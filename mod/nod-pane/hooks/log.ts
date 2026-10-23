import type { EngineInterface } from 'claude-code'

import { texts } from './texts/index'

type Logger = Pick<EngineInterface, 'ui'>

/** A drawing longer than this goes to the debug log; a shorter one is silent, or the log drowns. */
export const SLOW_RENDER_MS = 200

const describe = (err: unknown): string => (err instanceof Error ? err.message : String(err))

/** A line to the debug log; no log — silently. */
export async function logDebug($: Logger, text: string): Promise<void> {
  try {
    await $.ui.log(texts().logLine(text), { to: 'debug' })
  } catch {
    // no log
  }
}

/** Module timestamp: synchronous and without a host call, so a timing does not lengthen the click chain. */
export const stamp = (): number => Date.now()

/** Milliseconds between two timestamps. */
export const span = (from: number, to: number): number => Math.max(0, Math.round(to - from))

/**
 * Times `fn` and writes `<label> — <ms> ms[, tail]` to the debug log; an error is logged and rethrown.
 * Does not wait for the log line: a timing adds no host calls to the caller's chain.
 */
export async function timed<T>(
  $: Logger, label: string, fn: () => Promise<T>, tail?: (result: T) => string,
): Promise<T> {
  const from = stamp()
  try {
    const result = await fn()
    void logDebug($, texts().timedLine(label, span(from, stamp()), tail === undefined ? '' : tail(result)))

    return result
  } catch (err) {
    const t = texts()
    void logDebug($, t.timedLine(label, span(from, stamp()), t.errorPrefix + describe(err)))
    throw err
  }
}

/** A line about a slow drawing, or null if it kept within the limit. */
export const slowRenderLine = (ms: number): string | null => (ms > SLOW_RENDER_MS ? texts().slowRender(ms) : null)

// Moment of the last press of a write button: ui.render uses it to log when "saving…" reached a drawing.
// A module variable, not an atom: an atom write would redraw the pane itself.
let pressAt: number | null = null
let renderAfterPress = false

/** Called at the start of a write, before `pending` is set. */
export function markPress(): void {
  pressAt = stamp()
  renderAfterPress = true
}

/**
 * Log lines for a drawing started at `startedMs`: the first drawing after a press always with its duration,
 * the first with `pending` — "saving…" shown +N ms from the press (once per press); others only when slow.
 */
export function renderLines(startedMs: number, pending: string | null): string[] {
  const t = texts()
  const now = stamp()
  const lines: string[] = []
  if (renderAfterPress && pressAt !== null && startedMs >= pressAt) {
    renderAfterPress = false
    lines.push(t.renderAfterClick(span(startedMs, now)))
  } else {
    const slow = slowRenderLine(span(startedMs, now))
    if (slow !== null) lines.push(slow)
  }
  if (pending !== null && pressAt !== null) {
    lines.push(t.busyShown(span(pressAt, now)))
    pressAt = null
  }

  return lines
}
