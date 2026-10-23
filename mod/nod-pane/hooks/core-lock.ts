// One `nod` process changing state.json at a time. The core has no inter-process lock: a process that read the
// store before another one's write would rewrite state.json with old data. The slot is held by the start
// `nod status`, `nod status --peek` (timer, "Refresh", re-anchor) and `nod decision answer`. The `--help` probe
// does not take it. Do not nest withCore: a nested call would wait for itself.
// The wait for the slot is bounded by CORE_WAIT_MS: a process the host never returned does not hold clicks forever.
import type { EngineInterface } from 'claude-code'

/** The slot is not awaited longer than this: the write goes on over a hanging process. */
export const CORE_WAIT_MS = 70000

type Clocked = Pick<EngineInterface, 'clock'>

let inFlight: Promise<void> | null = null

const settle = (): void => undefined

/** true — a `nod` process changing state.json runs now; synchronous, without a host call. */
export function coreBusy(): boolean {
  return inFlight !== null
}

type Deadline = { expired: () => boolean; reached: Promise<void>; cancel: () => void }

/** A wait limit on the engine clock; `limitMs` <= 0 — passed already. Without a clock there is no limit. */
function deadline($: Clocked, limitMs: number): Deadline {
  if (limitMs <= 0) return { expired: () => true, reached: Promise.resolve(), cancel: settle }
  let hit = false
  let wake: () => void = settle
  const reached = new Promise<void>(resolve => { wake = resolve })
  let timer: ReturnType<EngineInterface['clock']['after']> | null = null
  try {
    timer = $.clock.after(limitMs, () => {
      hit = true
      wake()
    })
  } catch {
    // no clock — no limit: wait as before
  }

  return {
    expired: () => hit,
    reached,
    cancel: () => {
      try {
        timer?.cancel()
      } catch {
        // the timer has fired already
      }
    },
  }
}

/** Resolves when no `nod` process changing state.json runs, or after `limitMs`. false — the limit passed. */
export async function coreIdle($: Clocked, limitMs: number = CORE_WAIT_MS): Promise<boolean> {
  if (inFlight === null) return true
  const d = deadline($, limitMs)
  try {
    while (inFlight !== null && !d.expired()) await Promise.race([inFlight, d.reached])
  } finally {
    d.cancel()
  }

  return inFlight === null
}

/** Waits for a running process (no longer than `limitMs`), then runs `fn`, holding the slot until its end. */
export async function withCore<T>($: Clocked, fn: () => Promise<T>, limitMs: number = CORE_WAIT_MS): Promise<T> {
  if (inFlight !== null) {
    const d = deadline($, limitMs)
    try {
      while (inFlight !== null && !d.expired()) await Promise.race([inFlight, d.reached])
    } finally {
      d.cancel()
    }
  }
  // The check and the take of the slot are in one synchronous piece, with no gap between the waiters.
  const run = fn()
  const slot = run.then(settle, settle)
  inFlight = slot
  try {
    return await run
  } finally {
    if (inFlight === slot) inFlight = null
  }
}
