import type { EngineInterface } from 'claude-code'

import { local, setLocal } from './local'
import { logDebug, markPress, span, stamp } from './log'
import { CORE_WAIT_MS, coreBusy, coreIdle, withCore } from './core-lock'
import { refresh, refreshFromCore } from './refresh'
import { OK, cancel, finish, ignored, panelFailed, press, put, record, running, say, sayResult, track } from './report'
import type { Result, Timer, Track } from './report'
import { NOD_TIMEOUT_MS, runNod } from './nod'
import { inBatch } from './snapshot'
import { settleWithin, tryRead } from './state'
import type { PaneState, NodPrefix, TryRead } from './state'
import type { Writer } from './refresh'
import { texts } from './texts/index'
import { secondsOf } from './texts/format'

export type Actions = {
  answer(id: string, value: string, opts?: { note?: string; free?: boolean; label?: string }): void
  retry(): void
  answerAll(): void
  draft(text: string): void
  send(): void
  clearDraft(): void
  toggle(id: string): void
  refresh(): void
  openFree(id: string | null): void
}

type Doer = Pick<EngineInterface, 'fs' | 'process' | 'plugin' | 'prompt' | 'ui' | 'clock'>

/** Waiting for a running nod process longer than this shows the line "waiting for the snapshot rebuild…". */
export const WAIT_NOTICE_MS = 1000
const STUCK_MARGIN_MS = 10000
/**
 * A write lock older than this counts as stuck: the next click takes it off. Longer than the worst legal path:
 * waiting for the slot in guarded, a second wait for the slot in writeOne on a race and `nod` itself up to its timeout.
 */
export const STUCK_AFTER_MS = CORE_WAIT_MS + 2 * NOD_TIMEOUT_MS + STUCK_MARGIN_MS

// Synchronous write lock (together with local.pending): keeps what is being written and since when —
// a skip names the write that holds it. A hot reload clears it together with the module.
type Busy = { id: string; since: number }
let busy: Busy | null = null

type WriteTarget = { id: string; args: string[] }

const describe = (err: unknown): string => (err instanceof Error ? err.message : String(err))

/** Whether a live write holds the lock (a stuck one does not count); no side effects. */
const held = (): boolean => busy !== null && stamp() - busy.since <= STUCK_AFTER_MS

/**
 * Takes the lock synchronously. Held by a live write — `{ other, since }` with its id and start; a stuck one (older
 * than STUCK_AFTER_MS) is taken off, and its age comes in `stuckMs`.
 */
function enter(id: string): { other: string; since: number } | { stuckMs: number | null } {
  const now = stamp()
  if (busy !== null && now - busy.since <= STUCK_AFTER_MS) return { other: busy.id, since: busy.since }
  const stuckMs = busy === null ? null : now - busy.since
  busy = { id, since: now }

  return { stuckMs }
}

/** Tests only: age the held lock by `ms` (the module clock cannot be replaced in the kit). */
export function backdateLockForTest(ms: number): void {
  if (busy !== null) busy = { ...busy, since: busy.since - ms }
}

/**
 * Waits for a running nod process no longer than CORE_WAIT_MS; longer than WAIT_NOTICE_MS — says so in the status line.
 * false — the limit passed, the write goes on without waiting for the slot.
 */
async function waitCore($: Doer, t: Track): Promise<boolean> {
  if (!coreBusy()) return true
  let notice: Timer | null = null
  try {
    notice = $.clock.after(WAIT_NOTICE_MS, () => say($, texts().waitCoreStatus, t))
  } catch {
    // no clock — wait silently, lastAction says "running" already
  }
  try {
    return await coreIdle($)
  } finally {
    cancel(notice)
  }
}

/** Whether the write still owns its lock: false — it was taken off as stuck, and the outcome belongs to nobody. */
type Alive = () => boolean

/** Where to write: the nod command found and the state folder. */
type Where = { prefix: readonly string[]; dir: string }

/** The snapshot reread after a write is awaited no longer than this: then the buttons come back, the read goes on in the background. */
const REREAD_MS = 5000

/**
 * Value of an atom on the click path (the read is bounded by 2 s already). No answer — the module copy from the
 * session start (`fallback`), and the status names the swap; no copy — `{ stuck }` with the reason for a skip.
 */
function orFallback<T>(
  $: Doer, t: Track, label: string, got: TryRead<T>, fallback: T | undefined,
): { value: T } | { stuck: string } {
  if (got.ok) return { value: got.value }
  if (fallback === undefined) return { stuck: texts().panelStuck(label, got.error) }
  panelFailed($, t, label, got.error + '; ' + texts().fallbackNote)

  return { value: fallback }
}

/**
 * Where and whether to write: nod found, a state folder exists, the snapshot (with `fresh`) is fresh. Each read is
 * 2 s; nodPrefix and stateDir come from the session-start copies when $.state is silent. No nod or a stale snapshot —
 * such a state has no buttons, the press came from an old tree. The snapshot did not read — the write goes on, the status says so.
 */
async function locate($: Doer, st: PaneState, t: Track, fresh: boolean): Promise<Where | { reason: string }> {
  const [p, d, s] = await Promise.all([
    tryRead($, st.nodPrefix), tryRead($, st.stateDir), fresh ? tryRead($, st.snapshot) : null,
  ])
  const prefix = orFallback<NodPrefix>($, t, 'nodPrefix', p, local.lastNodPrefix === 'unknown' ? undefined : local.lastNodPrefix)
  if ('stuck' in prefix) return { reason: prefix.stuck }
  const dir = orFallback($, t, 'stateDir', d, local.lastStateDir ?? undefined)
  if ('stuck' in dir) return { reason: dir.stuck }
  const words = texts()
  if (prefix.value === null) return { reason: words.nodNotFound }
  if (prefix.value === 'unknown') return { reason: words.nodChecking }
  if (dir.value === null) return { reason: words.noStateDir }
  if (s !== null && !s.ok) panelFailed($, t, 'snapshot', s.error)
  if (s !== null && s.ok && s.value !== null && !s.value.fresh) return { reason: words.notFresh }

  return { prefix: prefix.value, dir: dir.value }
}

/**
 * One `nod decision answer` call; on an error puts it into local.writeError together with the args for "Retry".
 * The outcome goes to the status line as soon as nod returns: the truth is on screen even if the pane is not redrawn.
 * A write whose lock was taken off touches neither the status nor writeError.
 */
async function writeOne(
  $: Doer, t: Track, where: Where, id: string, args: string[], limitMs: number, alive: Alive,
): Promise<Result> {
  const { prefix, dir } = where
  say($, texts().writingStatus(id), t)
  // The core-lock slot: while another nod process changing state.json runs, the write waits. Do not nest.
  const ran = await withCore($, () => runNod($, prefix, dir, args), limitMs)
  const result: Result = ran.ok ? OK : { ok: false, message: ran.message }
  if (!alive()) return result
  sayResult($, t, result, id)
  if (!ran.ok) setLocal($, { writeError: { id, message: ran.message, args } })
  else if (local.writeError !== null) setLocal($, { writeError: null })

  return result
}

/** Atom writes for refresh from the click path: bounded, a refusal — in the status line of this press. */
function writer($: Doer, t: Track): Writer {
  return async (cell, value, label) => {
    await put($, t, cell, value, label)
  }
}

/** Takes off pending and the lock; a second call does nothing. */
type Release = () => Promise<void>

type Guard = {
  mark: string
  t: Track
  /** What is written — for the status line; called with the outcome. */
  target: (r: Result) => string
  /** Which decision an error lands on if the body throws. */
  at: () => WriteTarget
}

/**
 * The lock and `local.pending` around a write. `body` may take them off before its end itself (`release`), so that
 * the buttons come back before the background work; otherwise guarded takes them off. An uncaught error of `body`
 * goes to writeError on the decision from `at()`. The outcome goes to the status and lastAction; a held lock and a
 * refusal of the body (`ignored`) — a skip with the reason. Does not throw.
 */
async function guarded(
  $: Doer, st: PaneState, g: Guard, body: (release: Release, limitMs: number, alive: Alive) => Promise<Result>,
): Promise<void> {
  const entered = enter(g.mark)
  if ('other' in entered) return ignored($, g.t.what, texts().busyWith(entered.other, entered.since))
  if (entered.stuckMs !== null) g.t.notes.push(texts().stuckReset(secondsOf(entered.stuckMs)))
  const mine = busy
  let released = false
  // The write took its own lock off (release): busy may then hold the next write, that is not a takeover.
  let releasedOwn = false
  const alive: Alive = () => releasedOwn || busy === mine
  const release: Release = async () => {
    if (released) return
    released = true
    // The lock was taken off as stuck: pending belongs to another write now, leave it.
    if (busy !== mine) return
    releasedOwn = true
    busy = null
    setLocal($, { pending: null, progress: null })
  }
  let result: Result = OK
  let failure: { err: unknown } | null = null
  try {
    // pending first: synchronously in the module, "saving…" waits neither for $.state nor for a process.
    setLocal($, { pending: g.mark })
    await running($, g.t)
    // Wait for a running nod process before the write's reads; the write takes the slot itself in writeOne.
    let limitMs = CORE_WAIT_MS
    if (!(await waitCore($, g.t))) {
      const late = texts().coreTimeout(secondsOf(CORE_WAIT_MS))
      g.t.notes.push(late)
      say($, texts().statusLine(late), g.t)
      await running($, g.t)
      limitMs = 0
    }
    result = await body(release, limitMs, alive)
  } catch (err) {
    failure = { err }
  }
  if (!alive()) return overtaken($, g, failure === null ? result : { ok: false, message: describe(failure.err) })
  try {
    await release()
  } catch (err) {
    failure ??= { err }
  }
  if (failure === null && !result.ok && result.ignored === true) return ignored($, g.t.what, result.message)
  if (failure !== null) {
    result = { ok: false, message: describe(failure.err) }
    setLocal($, { writeError: { ...g.at(), message: result.message } })
  }
  await finish($, g.t, result, g.target(result))
}

/**
 * Outcome of a write whose lock was taken off as stuck while it ran: the new write owns pending, writeError,
 * the status and the footer already. Only the debug log; lastAction — only if it is still about this write.
 */
async function overtaken($: Doer, g: Guard, r: Result): Promise<void> {
  await logDebug($, texts().overtakenLine(g.t.what, r.ok ? 'ok' : r.message))
  const last = local.lastAction
  if (last !== null && last.what === g.t.what && last.at === g.t.at) await record($, g.t, r)
}

/**
 * Re-anchor without waiting: the "While you were away" zone goes back to the visit point, the card does not wait for it.
 * refreshFromCore keeps the peek queue; with `label` the duration (with the queue wait) goes to the debug log.
 */
function reanchorLater($: Doer, st: PaneState, label?: string): void {
  void (async () => {
    const from = stamp()
    try {
      await refreshFromCore($, st, { sync: false })
      if (label !== undefined) await logDebug($, texts().timedLine(label, span(from, stamp()), ''))
    } catch (err) {
      await logDebug($, describe(err))
    }
  })()
}
/** Closes the "Your own answer" field after a write; a 2 s read, a refusal goes to the debug log: the decision is written already. */
async function closeFree($: Doer, st: PaneState, t: Track, id: string): Promise<void> {
  const open = await tryRead($, st.freeFor)
  if (!open.ok) return logDebug($, texts().panelStuck('freeFor', open.error))
  if (open.value === id) await put($, t, st.freeFor, null, 'freeFor')
}

/** Snapshot reread from the click path: no longer than REREAD_MS, then the status and the buttons back, the read in the background. */
async function reread($: Doer, st: PaneState, t: Track): Promise<void> {
  const done = await settleWithin($, refresh($, st, { force: true, reanchor: false, write: writer($, t) }), REREAD_MS)
  if (!done) panelFailed($, t, texts().rereadLabel, texts().timeoutText(REREAD_MS))
}

/** Module timestamps on the click path (`Date.now`, no host calls). */
type ClickMarks = { pressed: number; pending?: number; wrote?: number; read?: number; released?: number }

/**
 * The click path as one debug-log line at the moment the buttons come back: offsets from the press to pending,
 * the reread snapshot and the buttons back, plus the write duration (`nod answer`). A failure — "not saved".
 */
function clickParts(m: ClickMarks): string[] {
  const t = texts()
  const since = (what: string, at: number | undefined): string[] =>
    (at === undefined ? [] : [t.sinceClick(what, span(m.pressed, at))])

  return [
    ...since(t.clickPending, m.pending),
    ...(m.pending !== undefined && m.wrote !== undefined ? [t.nodAnswerSpan(span(m.pending, m.wrote))] : []),
    ...(m.read === undefined ? [t.clickFailed] : []),
    ...since(t.clickRead, m.read),
    ...since(t.clickReleased, m.released),
  ]
}

/** A skip with the reason: the guarded body refused to write. */
const skip = (message: string): Result => ({ ok: false, message, ignored: true })

async function writeDecision($: Doer, st: PaneState, id: string, args: string[], what: string): Promise<void> {
  if (!held()) markPress()
  const m: ClickMarks = { pressed: stamp() }
  const g: Guard = { mark: id, t: track(what), target: () => id, at: () => ({ id, args }) }
  await guarded($, st, g, async (release, limitMs, alive) => {
    m.pending = stamp()
    const where = await locate($, st, g.t, true)
    if ('reason' in where) return skip(where.reason)
    const wrote = await writeOne($, g.t, where, id, args, limitMs, alive)
    m.wrote = stamp()
    // The lock was taken off while nod ran: rereading the snapshot and closing the field belong to the new write.
    if (!wrote.ok || !alive()) {
      void logDebug($, texts().clickLine(id, clickParts(m)))

      return wrote
    }
    await closeFree($, st, g.t, id)
    // The core has rebuilt state.json inside `decision answer` already: reread the file, and the card goes.
    await reread($, st, g.t)
    m.read = stamp()
    await release()
    m.released = stamp()
    void logDebug($, texts().clickLine(id, clickParts(m)))
    reanchorLater($, st, texts().reanchorLabel(id))

    return wrote
  })
}

/** The batch: the proposed answer of each waiting decision in order; the first error stops the queue; the snapshot is reread once. */
async function writeAll($: Doer, st: PaneState): Promise<void> {
  const words = texts()
  const t = track(words.whatAll)
  const got = await tryRead($, st.snapshot)
  if (!got.ok) {
    await logDebug($, got.error)

    return ignored($, t.what, words.panelStuck('snapshot', got.error))
  }
  const snap = got.value
  if (snap === null) return ignored($, t.what, words.noSnapshot)
  if (!snap.fresh) return ignored($, t.what, words.notFresh)
  const where = await locate($, st, t, false)
  if ('reason' in where) return ignored($, t.what, where.reason)
  if (!held()) markPress()
  const queue = snap.waiting.filter(inBatch)
  let current: WriteTarget = { id: '', args: [] }
  const g: Guard = { mark: 'all', t, target: r => (r.ok ? texts().allTarget(queue.length) : current.id), at: () => current }
  await guarded($, st, g, async (release, limitMs, alive) => {
    let result: Result = OK
    try {
      for (const [done, d] of queue.entries()) {
        setLocal($, { progress: { done, total: queue.length } })
        const free = d.options.includes(d.proposed) ? undefined : { free: true }
        current = { id: d.id, args: answerArgs(d.id, d.proposed, free) }
        result = await writeOne($, t, where, d.id, current.args, limitMs, alive)
        if (!result.ok || !alive()) break
      }
    } catch (err) {
      if (alive()) setLocal($, { progress: null })
      throw err
    }
    if (!alive()) return result
    setLocal($, { progress: null })
    await reread($, st, t)
    await release()
    reanchorLater($, st)

    return result
  })
}

async function addToDraft(st: PaneState, text: string): Promise<void> {
  try {
    const now = await st.draft.read()
    await st.draft.write(now === '' ? text : now + ' ' + text)
  } catch {
    // the draft was not written — a button must not bring the mod down
  }
}

// Lock: a second "Send" while a submit is unfinished does nothing.
let sending = false

/**
 * Sends the draft to the chat queue. A refusal comes as `{ drop }`, not a reject: then the draft stays. After a success
 * removes only the sent text and keeps what was added while sending.
 */
async function sendDraft($: Doer, st: PaneState): Promise<void> {
  const words = texts()
  const t = track(words.whatSend)
  if (sending) return ignored($, t.what, words.sendingNow)
  sending = true
  try {
    const got = await tryRead($, st.draft)
    if (!got.ok) return await ignored($, t.what, words.panelStuck('draft', got.error))
    const text = got.value
    if (text === '') return await ignored($, t.what, words.emptyDraft)
    await running($, t)
    const result = await $.prompt.submit({ text })
    if (result.drop !== undefined) {
      await logDebug($, words.promptDropped(result.drop))
      await finish($, t, { ok: false, message: words.promptDropped(result.drop) })

      return
    }
    // The text is in the queue already: the draft did not read in 2 s — it stays as is, the outcome is ok anyway.
    const after = await tryRead($, st.draft)
    if (after.ok) {
      const current = after.value
      await st.draft.write(current.startsWith(text + ' ') ? current.slice(text.length + 1) : current === text ? '' : current)
    } else {
      panelFailed($, t, 'draft', after.error)
    }
    await finish($, t, OK)
  } catch (err) {
    await logDebug($, describe(err))
    await finish($, t, { ok: false, message: describe(err) })
  } finally {
    sending = false
  }
}

/** "Refresh": the core rebuilds the snapshot, the outcome is by loadError after it. The timer does not come here: lastAction is the button's only. */
async function refreshByButton($: Doer, st: PaneState): Promise<void> {
  const t = track(texts().whatRefresh)
  try {
    await running($, t)
    await refreshFromCore($, st, { sync: true })
    const got = await tryRead($, st.loadError)
    const failed = got.ok ? got.value : texts().panelStuck('loadError', got.error)
    await finish($, t, failed === null ? OK : { ok: false, message: failed })
  } catch (err) {
    await logDebug($, describe(err))
    await finish($, t, { ok: false, message: describe(err) })
  }
}

/** argv of an answer write; `--` before the id and the answer — otherwise the core's argparse reads an answer like "-h" as a flag. */
export function answerArgs(id: string, value: string, opts?: { note?: string; free?: boolean }): string[] {
  return [
    'decision', 'answer',
    ...(opts?.note ? ['--note', opts.note] : []),
    ...(opts?.free ? ['--free'] : []),
    '--', id, value,
  ]
}

export function makeActions($: Doer, st: PaneState): Actions {
  // A button does not wait for the promise: every refusal goes to the debug log, not to an uncaught reject.
  const fire = (work: () => Promise<void>): void => {
    void (async () => {
      try {
        await work()
      } catch (err) {
        await logDebug($, describe(err))
      }
    })()
  }

  // The first statements of a write handler are the three press channels (press): seen even if all else is silent.
  return {
    answer: (id, value, opts) => {
      press($, opts?.label ?? texts().answerLabel(value))
      fire(() => writeDecision($, st, id, answerArgs(id, value, opts), texts().whatAnswer(id)))
    },
    retry: () => {
      press($, texts().retry)
      fire(async () => {
        const failed = local.writeError
        if (failed === null) return ignored($, texts().whatRetry(), texts().nothingToRetry)
        await writeDecision($, st, failed.id, failed.args, texts().whatRetry(failed.id))
      })
    },
    answerAll: () => {
      press($, texts().answerAll)
      fire(() => writeAll($, st))
    },
    draft: text => fire(() => addToDraft(st, text)),
    send: () => {
      press($, texts().send)
      fire(() => sendDraft($, st))
    },
    clearDraft: () => fire(() => st.draft.write('')),
    toggle: id => fire(async () => {
      const open = await st.expanded.read()
      await st.expanded.write(open.includes(id) ? open.filter(x => x !== id) : [...open, id])
    }),
    refresh: () => {
      press($, texts().refresh)
      fire(() => refreshByButton($, st))
    },
    openFree: id => fire(() => st.freeFor.write(id)),
  }
}
