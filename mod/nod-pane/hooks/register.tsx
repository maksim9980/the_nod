import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import { makeActions } from './actions'
import { drawPane } from './draw/pane'
import type { PaneModel } from './draw/pane'
import { findLegacyDir, findStateDir } from './find'
import { logDebug, renderLines, stamp } from './log'
import { doubleLoad, roleOf, tokenOf, viewOf } from './owner'
import { firstLoad, refresh } from './refresh'
import { factLine, isListed, listNod, listedLine, registerNod } from './command'
import type { RegFact } from './command'
import { diagLines } from './diag'
import { noteFocus, onPaneFocus } from './focus'
import { countRender, local, resetLocal, setLocal } from './local'
import { lastStatus, setDiag, tell } from './report'
import { resolveNod } from './nod'
import type { Snapshot } from './snapshot'
import { safeWrite, tryRead } from './state'
import { replyTo } from './subcommand'
import type { Cell, PaneState, SafeWrite, NodPrefix, TryRead } from './state'
import { currentLang, noteLang, startLang, texts } from './texts/index'

const PANE = 'nod'
const TITLE = 'Nod'

// Atoms are declared here: the state scanner reads keys only from the hook file.
const stateDirAtom = atom({ plugin: 'nod', key: 'stateDir' } as const, null)
const panePlacedAtom = atom({ plugin: 'nod', key: 'panePlaced' } as const, false)
const nodPrefixAtom = atom({ plugin: 'nod', key: 'nodPrefix' } as const, 'unknown')

const snapshotAtom = atom({ plugin: 'nod', key: 'snapshot' } as const, null)
const loadErrorAtom = atom({ plugin: 'nod', key: 'loadError' } as const, null)
const lastMtimeAtom = atom({ plugin: 'nod', key: 'lastMtime' } as const, 0)
const sinceFromAtom = atom({ plugin: 'nod', key: 'sinceFrom' } as const, null)

const draftAtom = atom({ plugin: 'nod', key: 'draft' } as const, '')
const expandedAtom = atom({ plugin: 'nod', key: 'expanded' } as const, [] as string[])
const freeForAtom = atom({ plugin: 'nod', key: 'freeFor' } as const, null)
// Pane owner on a double load (owner.ts): the token `<id>@<root>` and the root of the second instance.
const instanceAtom = atom({ plugin: 'nod', key: 'instance' } as const, null)
const otherRootAtom = atom({ plugin: 'nod', key: 'otherRoot' } as const, null)

const REFRESH_EVERY_MS = 15000
const ID_RADIX = 36
const ID_FROM = 2

// Id of this module instance: a new one on every load, a hot one included.
const instance = Math.random().toString(ID_RADIX).slice(ID_FROM)

const noop = (): void => undefined

// The state contract is self-contained (no import), so the snapshot is unknown there, and the cast here gives its type.
// Cells over the atoms: the other files of the mod get them as a parameter and do not know atoms.
const cells = ($: EngineInterface): PaneState => ({
  stateDir: { read: () => read($, stateDirAtom), write: v => update($, stateDirAtom, () => v) },
  nodPrefix: { read: () => read($, nodPrefixAtom), write: v => update($, nodPrefixAtom, () => v) },
  snapshot: { read: async () => (await read($, snapshotAtom)) as Snapshot | null, write: v => update($, snapshotAtom, () => v) },
  loadError: { read: () => read($, loadErrorAtom), write: v => update($, loadErrorAtom, () => v) },
  lastMtime: { read: () => read($, lastMtimeAtom), write: v => update($, lastMtimeAtom, () => v) },
  sinceFrom: { read: () => read($, sinceFromAtom), write: v => update($, sinceFromAtom, () => v) },
  draft: { read: () => read($, draftAtom), write: v => update($, draftAtom, () => v) },
  expanded: { read: () => read($, expandedAtom), write: v => update($, expandedAtom, () => v) },
  freeFor: { read: () => read($, freeForAtom), write: v => update($, freeForAtom, () => v) },
  instance: { read: () => read($, instanceAtom), write: v => update($, instanceAtom, () => v) },
  otherRoot: { read: () => read($, otherRootAtom), write: v => update($, otherRootAtom, () => v) },
})

/**
 * Resets all our $.state keys except draft: after hot reloads they hold values of previous loads (a foreign owner
 * token, an open field, an old error). The writes are parallel and bounded (safeWrite, 2 s); the outcome is the keys
 * that failed, with the reason.
 */
async function resetState($: EngineInterface, st: PaneState): Promise<string[]> {
  const placed: Cell<boolean> = { read: () => read($, panePlacedAtom), write: v => update($, panePlacedAtom, () => v) }
  const writes: [string, Promise<SafeWrite>][] = [
    ['stateDir', safeWrite($, st.stateDir, null)],
    ['panePlaced', safeWrite($, placed, false)],
    ['nodPrefix', safeWrite($, st.nodPrefix, 'unknown')],
    ['snapshot', safeWrite($, st.snapshot, null)],
    ['loadError', safeWrite($, st.loadError, null)],
    ['lastMtime', safeWrite($, st.lastMtime, 0)],
    ['sinceFrom', safeWrite($, st.sinceFrom, null)],
    ['expanded', safeWrite($, st.expanded, [])],
    ['freeFor', safeWrite($, st.freeFor, null)],
    ['otherRoot', safeWrite($, st.otherRoot, null)],
  ]
  const done = await Promise.all(writes.map(([, w]) => w))

  return done.flatMap((r, i) => (r.ok ? [] : [texts().resetFailed(writes[i]?.[0] ?? '', r.error ?? '')]))
}

/** The load line to the transcript; a reset refusal also to the footer. No log — silently. */
function sayLoaded($: EngineInterface, failed: string[], fact: string): void {
  tell($, texts().loadedLine($.plugin.root, instance, failed, fact))
  if (failed.length > 0) {
    setLocal($, { lastAction: { what: texts().resetWhat, at: stamp(), ms: null, result: 'error', detail: failed.join(', ') } })
  }
}

function describeNod(prefix: NodPrefix): string {
  const t = texts()

  return '\n' + (prefix === 'unknown' ? t.nodCheckingLine
    : prefix === null ? t.nodNotFound + local.nodTried.map(line => '\n' + line).join('') : t.nodLine(prefix))
}

// A module flag: a hot reload drops the timers and this flag together with the module, and session.start does not
// come a second time — so tool.call and ui.render also arm the timer lazily.
let armed = false

// A non-owner writes its root into otherRoot once a session: the owner shows the double-load line.
let notedOther = false

// Whose foreign token this drawing has named in the transcript already: one line per token.
let toldStale: string | null = null
// The second root the last drawing saw: /nod names the double load without a second read.
let seenOther: string | null = null

/** Drawing over a foreign token, says so in the transcript (once per token); does not touch $.state. */
function sayStale($: EngineInterface, stored: string | null, view: ReturnType<typeof viewOf>): void {
  if (stored === null || toldStale === stored || (view.stale === null && view.foreignRoot === null)) return
  toldStale = stored
  tell($, view.foreignRoot === null ? texts().reclaimLine(stored) : texts().takeoverLine(stored))
}

// The last value read of each key: a key that did not answer within 2 s is taken from here by the drawing.
const lastSeen = new Map<string, unknown>()

/** The value of a bounded read; no answer — the last one seen, otherwise the initial one. */
function seen<T>(key: string, got: TryRead<T>, initial: T): T {
  if (got.ok) {
    lastSeen.set(key, got.value)

    return got.value
  }

  return lastSeen.has(key) ? (lastSeen.get(key) as T) : initial
}

/** A non-owner writes its root into otherRoot (not from a drawing); the flag only after a successful write. */
async function noteOther($: EngineInterface, st: PaneState): Promise<void> {
  if (notedOther) return
  if ((await safeWrite($, st.otherRoot, $.plugin.root)).ok) notedOther = true
}

/** Role of this instance by the instance atom (owner.ts). */
async function myRole($: EngineInterface, st: PaneState): Promise<ReturnType<typeof roleOf>> {
  return roleOf(await st.instance.read(), instance, $.plugin.root)
}

/** Background work only for the owner: a non-owner marks itself in otherRoot and stays silent. */
async function asOwner($: EngineInterface, st: PaneState, work: () => Promise<void>): Promise<void> {
  if ((await myRole($, st)) === 'pass') return noteOther($, st)
  await work()
}

/** Arms the reread every 15 s, if not armed yet and the state folder is known. */
async function armTimer($: EngineInterface, st: PaneState): Promise<void> {
  const dir = await st.stateDir.read()
  if (armed || dir === null) return
  armed = true
  try {
    await $.clock.every(REFRESH_EVERY_MS, () => void asOwner($, st, () => refresh($, st)).catch(noop))
  } catch (err) {
    armed = false
    throw err
  }
}

/** Timing lines of a drawing (see renderLines) to the debug log; the drawing does not wait for them. */
async function logRender($: EngineInterface, startedMs: number, pending: string | null): Promise<void> {
  for (const line of renderLines(startedMs, pending)) await logDebug($, line)
}

async function openPane($: EngineInterface): Promise<void> {
  try {
    const opened = await $.ui.open({ id: PANE, title: TITLE })
    await update($, panePlacedAtom, () => opened.isPlaced)
    if (!opened.isPlaced) {
      await $.ui.log('nod: ' + opened.reason, { to: 'debug' })
      await $.ui.status(texts().openHint)
    }
  } catch (err) {
    await $.ui.log('nod: ' + (err instanceof Error ? err.message : String(err)), { to: 'debug' })
  }
}

/**
 * /nod without `.nod`: the older version's folder, if there is one, goes into the module and the pane opens to
 * suggest `/nod migrate`. Only /nod calls it: a session start in such a folder opens nothing. The outcome is the
 * folder found or null.
 */
async function noteLegacy($: EngineInterface, cwd: string): Promise<string | null> {
  const legacy = await findLegacyDir($, cwd)
  setLocal($, { legacyDir: legacy })
  if (legacy !== null) await openPane($)

  return legacy
}

/** Tail of the session start: state folder, pane, core, snapshot, timer; the outcome is the folder found. Does not throw. */
async function attach($: EngineInterface, st: PaneState, cwd: string, configured: string): Promise<string | null> {
  let dir: string | null = null
  try {
    // A non-owner only marks itself: the pane, the core and the timer belong to the owner.
    if ((await myRole($, st)) === 'pass') return await noteOther($, st).then(() => null)
    dir = await findStateDir($, cwd)
    // Copies in the module: the click path takes them if $.state does not answer (actions.ts, locate).
    local.lastStateDir = dir
    await update($, stateDirAtom, () => dir)
    // No state: no pane. An older version's folder is named only by /nod, so a repository that stays on it is not nagged.
    if (dir === null) return null
    setLocal($, { legacyDir: null })
    await openPane($)
    const probe = await resolveNod($, configured)
    Object.assign(local, { lastNodPrefix: probe.prefix, nodTried: probe.tried })
    await update($, nodPrefixAtom, () => probe.prefix)
    if (probe.prefix === null) await $.ui.log('nod: ' + texts().nodMissingLog)
    await firstLoad($, st)
    await armTimer($, st)
  } catch (err) {
    await logDebug($, err instanceof Error ? err.message : String(err))
  }

  return dir
}

// Outcome of the last /nod registration attempt (command.ts); null — no attempts since the module loaded.
let regFact: RegFact | null = null
// The last fact named in the transcript: a retry with the same fact writes no line.
let toldFact: string | null = null
// The retry on the first turn.complete has happened — since the module load or the last session.start.
let turnRetried = false

/**
 * Registration attempts: (a) in session.start before next(e) — the fact goes into the load line; (b) right after
 * next(e) and (c) on the first turn.complete — only if /nod is not in the engine registry yet. Registering the same
 * name replaces the previous one, so a retry is safe. Drawing and tool.call do not register.
 */
// A running retry: (b) and (c) may coincide in time — the second waits for the first instead of registering again.
let retrying: Promise<void> | null = null

function registerAgain($: EngineInterface, when: string): Promise<void> {
  if (retrying === null) retrying = retryOnce($, when).finally(() => { retrying = null })

  return retrying
}

async function retryOnce($: EngineInterface, when: string): Promise<void> {
  if (isListed(regFact)) return
  regFact = await registerNod($)
  const line = factLine(regFact)
  if (line === toldFact) return
  toldFact = line
  tell($, texts().retryLine(when, line))
}

/** Tail of /nod — diagnostics in one answer (diag.ts): everything from the module except the instance atom. */
function diagTail($: EngineInterface, owner: TryRead<string | null>, registry: string): string {
  const t = texts()

  return diagLines({
    id: instance, root: $.plugin.root, registry, owner, double: doubleLoad($.plugin.root, seenOther, t),
    pending: local.pending, lastStatus: lastStatus(), lastAction: local.lastAction,
    renders: local.renders, renderedAt: local.renderedAt,
  }, t).map(line => '\n' + line).join('')
}

/** /nod without a state folder: the hint about the older version's folder (and the pane says it too) or "no state". */
async function answerNoState($: EngineInterface, diag: string): Promise<string> {
  const cwd = await $.session.cwd()
  const legacy = await noteLegacy($, cwd)

  return (legacy === null ? texts().noState(cwd) : texts().legacyFound) + diag
}

export const register: Register = (on, options) => {
  setDiag(options.diag === true)
  // The focus ring came to the pane: the status "the pane has focus…"; the ring goes on (focus.ts).
  on('ui.focus', { component: 'Pane', requestId: PANE }, ($, e, next) => onPaneFocus($, e, next))
  on('session.start', async ($, e, next) => {
    turnRetried = false
    const st = cells($)
    // Texts before the first snapshot of this session: the language of the previous load's last snapshot.
    const prior = await tryRead($, st.snapshot)
    startLang(prior.ok ? prior.value : null)
    // (a) Before next(e); the fact is the tail of the load line.
    regFact = await registerNod($)
    toldFact = factLine(regFact)
    // Before next: instances further down the chain write later, the one started last becomes the owner.
    notedOther = false
    resetLocal($)
    // First reset the previous loads, then write our token: those further down the chain reset and write later.
    const failed = await resetState($, st)
    const claimed = await safeWrite($, st.instance, tokenOf(instance, $.plugin.root))
    // without the atom every instance counts as the owner — as before the protection
    if (!claimed.ok) failed.push(texts().resetFailed('instance', claimed.error ?? ''))
    sayLoaded($, failed, toldFact)
    const started = await next(e)

    void attach($, st, e.cwd, String(options.core ?? ''))
    // (b) After next(e), if (a) failed or the registry did not show /nod. Not awaited and goes after the pane open
    // started: a hanging registration holds neither the pane nor the session.start budget.
    void registerAgain($, texts().afterStart).catch(noop)

    return started
  })

  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    const st = cells($)
    void asOwner($, st, async () => {
      void armTimer($, st).catch(noop)
      await refresh($, st)
    }).catch(noop)

    return ran
  })

  // (c) The first answer of the main loop after session.start: a retry if /nod is still not in the registry. Not
  // awaited — the hook gates the answer text, so next(e) returns at once and as is.
  on('turn.complete', ($, e, next) => {
    if (e.agentId === undefined && !turnRetried) {
      turnRetried = true
      void registerAgain($, texts().afterTurn).catch(noop)
    }

    return next(e)
  })

  // Reads are bounded (2 s): /nod answers even when $.state does not answer in this session.
  // The engine registry is asked anew: "in the engine registry: yes/no" — at the moment of the answer.
  // The answer is in the language of the snapshot in $.state.nod.
  on('command.run', { command: 'nod' }, async ($, e) => {
    const st = cells($)
    const args = e.args.trim()
    const configured = String(options.core ?? '')
    if (args !== '') {
      const snap = await tryRead($, st.snapshot)
      if (snap.ok) noteLang(snap.value)

      return { text: await replyTo($, st, args, configured, { attach: cwd => attach($, st, cwd, configured) }) }
    }
    const [dirRead, prefixRead, owner, snap, listed] = await Promise.all([
      tryRead($, st.stateDir), tryRead($, st.nodPrefix), tryRead($, st.instance), tryRead($, st.snapshot), listNod($),
    ])
    if (snap.ok) noteLang(snap.value)
    // A load without session.start (a hot reload): there was no attempt — only the registry answer.
    const registry = regFact === null ? listedLine(listed) : factLine({ error: regFact.error, ...listed })
    const diag = diagTail($, owner, registry)
    const t = texts()
    if (!dirRead.ok) return { text: t.statusLine(t.panelStuck('stateDir', dirRead.error)) + diag }
    const dir = dirRead.value
    if (dir === null) return { text: await answerNoState($, diag) }
    const nod = prefixRead.ok ? describeNod(prefixRead.value) : '\n' + t.panelStuck('nodPrefix', prefixRead.error)
    const tail = nod + diag
    let opened: Awaited<ReturnType<EngineInterface['ui']['open']>>
    try {
      opened = await $.ui.open({ id: PANE, title: TITLE })
    } catch (err) {
      return { text: t.paneFailed(err instanceof Error ? err.message : String(err)) + tail }
    }
    if (!opened.isPlaced) return { text: t.paneNotPlaced(opened.reason, dir) + tail }

    return { text: t.paneOpened(dir) + tail }
  })

  // A drawing writes nothing to $.state, passes nothing down and bounds every read by 2 s: the engine refuses a write
  // while drawing, and a hanging read would leave an old frame with dead buttons on screen.
  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const startedMs = stamp()
    const st = cells($)
    // In one go: on Desktop each read is a host call, one after another they add up.
    const [owner, other, prefix, snapshot, loadError, stateDir, draft, expanded, freeFor, nowMs] = await Promise.all([
      tryRead($, st.instance), tryRead($, st.otherRoot), tryRead($, st.nodPrefix), tryRead($, st.snapshot),
      tryRead($, st.loadError), tryRead($, st.stateDir), tryRead($, st.draft), tryRead($, st.expanded),
      tryRead($, st.freeFor), $.clock.now(),
    ])
    noteFocus($, e.props.isFocused)
    const view = viewOf(owner, instance, $.plugin.root)
    sayStale($, owner.ok ? owner.value : null, view)
    // The second root: from the token of another folder, otherwise from otherRoot; /nod takes it from here.
    seenOther = view.foreignRoot ?? (other.ok ? other.value : seenOther)
    void armTimer($, st).catch(noop)
    // The click state comes from the module (local.ts): $.state does not hold it.
    const { pending, progress, writeError, lastAction } = local
    const nod = seen('nodPrefix', prefix, 'unknown' as NodPrefix)
    const shown = seen('snapshot', snapshot, null)
    // The snapshot's language; without a snapshot — the language of the last one the mod saw.
    noteLang(shown)
    const lang = currentLang()
    const model: PaneModel = {
      snapshot: shown, loadError: seen('loadError', loadError, null),
      stateDir: seen('stateDir', stateDir, null), nowMs, pending, progress, writeError,
      draft: seen('draft', draft, ''), expanded: seen('expanded', expanded, [] as string[]),
      freeFor: seen('freeFor', freeFor, null), lastAction,
      renders: countRender(nowMs),
      focused: e.props.isFocused,
      doubleLoad: doubleLoad($.plugin.root, seenOther, texts()),
      nodMissing: nod === null,
      legacy: local.legacyDir !== null,
      lang,
    }
    const tree = drawPane($.ui.resolve(e), model, makeActions($, st), e.props.bodyColumns)
    void logRender($, startedMs, pending)

    return tree
  })
}
