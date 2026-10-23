import type { EngineInterface } from 'claude-code'

import { texts } from './texts/index'

import type { Snapshot } from './snapshot'

export type NodPrefix = readonly string[] | null | 'unknown'

/** Error of writing an answer: decision id, text and the `nod` arguments "Retry" repeats the call with. */
export type WriteError = { id: string; message: string; args: string[] }

/** Progress of a batch write: how many decisions are written and how many are queued. */
export type Progress = { done: number; total: number }

/** Last action of the pane: the footer shows it without logs. `ms` is null while it runs and for a skip. */
export type LastAction = {
  what: string
  at: number
  ms: number | null
  result: 'running' | 'ok' | 'error' | 'ignored'
  detail: string
}

/** A state cell: register.tsx builds it over an atom, the other files do not know atoms. */
export type Cell<T> = { read(): Promise<T>; write(value: T): Promise<void> }

export type PaneState = {
  stateDir: Cell<string | null>
  nodPrefix: Cell<NodPrefix>
  snapshot: Cell<Snapshot | null>
  loadError: Cell<string | null>
  lastMtime: Cell<number>
  sinceFrom: Cell<string | null>
  draft: Cell<string>
  expanded: Cell<string[]>
  freeFor: Cell<string | null>
  /** Token of the pane owner `<id>@<root>` (owner.ts). */
  instance: Cell<string | null>
  /** Root of a second mod instance, if one is loaded from another folder. */
  otherRoot: Cell<string | null>
}

/** Limit of an atom write on the click path: longer, and the pane write counts as unanswered. */
export const STATE_WRITE_MS = 2000

/** Outcome of a bounded atom write: ok, how long it took and why not. */
export type SafeWrite = { ok: boolean; ms: number; error?: string }

type Clock = Pick<EngineInterface, 'clock'>

const TIMED_OUT = Symbol('timeout')

/**
 * Waits for `work` no longer than `ms` by the engine clock. A timeout gives TIMED_OUT, a refusal rejects as is.
 * Without a clock there is no limit.
 */
async function within<T>($: Clock, work: Promise<T>, ms: number): Promise<T | typeof TIMED_OUT> {
  let timer: { cancel: () => void } | null = null
  const late = new Promise<typeof TIMED_OUT>(resolve => {
    try {
      timer = $.clock.after(ms, () => resolve(TIMED_OUT))
    } catch {
      // no clock — no limit
    }
  })
  try {
    return await Promise.race([work, late])
  } finally {
    try {
      ;(timer as { cancel: () => void } | null)?.cancel()
    } catch {
      // the timer has fired already
    }
  }
}

const describe = (err: unknown): string => (err instanceof Error ? err.message : String(err))

/**
 * An atom write that neither throws nor hangs: a refusal (`{ deny }`, reject) and a timeout come in `error`.
 * The click path writes atoms only this way: the pane state may not answer, and the answer must still be written.
 */
export async function safeWrite<T>($: Clock, cell: Cell<T>, value: T, ms: number = STATE_WRITE_MS): Promise<SafeWrite> {
  const from = Date.now()
  try {
    const done = await within($, cell.write(value), ms)
    const took = Date.now() - from

    return done === TIMED_OUT ? { ok: false, ms: took, error: texts().timeoutText(ms) } : { ok: true, ms: took }
  } catch (err) {
    return { ok: false, ms: Date.now() - from, error: describe(err) }
  }
}

/** Waits for the work no longer than `ms`; true — it finished (success or refusal), false — the limit passed. */
export async function settleWithin($: Clock, work: Promise<unknown>, ms: number): Promise<boolean> {
  try {
    return (await within($, work, ms)) !== TIMED_OUT
  } catch {
    return true
  }
}

/** Outcome of a bounded read: the value or the reason (refusal, timeout). */
export type TryRead<T> = { ok: true; value: T } | { ok: false; error: string }

/** An atom read with the same limit; neither throws nor hangs. */
export async function tryRead<T>($: Clock, cell: Cell<T>, ms: number = STATE_WRITE_MS): Promise<TryRead<T>> {
  try {
    const got = await within($, cell.read(), ms)

    return got === TIMED_OUT ? { ok: false, error: texts().timeoutText(ms) } : { ok: true, value: got }
  } catch (err) {
    return { ok: false, error: describe(err) }
  }
}

/** An atom read with the same limit; no answer — null. */
export async function safeRead<T>($: Clock, cell: Cell<T>, ms: number = STATE_WRITE_MS): Promise<T | null> {
  const got = await tryRead($, cell, ms)

  return got.ok ? got.value : null
}
