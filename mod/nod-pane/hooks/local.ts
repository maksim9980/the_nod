// Click-path state lives in module variables, not in $.state: "saving…", the batch progress, the write error
// and the last action. A hot reload clears them together with the module, so a lock cannot linger, and a
// refusing or hanging $.state does not touch them. The pane is redrawn by `$.ui.invalidate`, not by an atom write.
import type { EngineInterface } from 'claude-code'

import type { LastAction, Progress, NodPrefix, WriteError } from './state'

export type Local = {
  /** What is being written: a decision id or 'all'; null — the buttons are shown. */
  pending: string | null
  progress: Progress | null
  writeError: WriteError | null
  lastAction: LastAction | null
  /** How many times this module instance drew the pane. */
  renders: number
  /** Time of the last drawing by the engine clock; null — not drawn yet. */
  renderedAt: number | null
  /** State folder and nod command found by the session.start chain: fallbacks when $.state does not answer. */
  lastStateDir: string | null
  lastNodPrefix: NodPrefix
  /** Lines about the nod candidates that failed — for the /nod answer when the core is not found. */
  nodTried: readonly string[]
  /** State folder of an older version, found where `.nod` is missing: the pane suggests `/nod migrate`. */
  legacyDir: string | null
}

export const local: Local = {
  pending: null, progress: null, writeError: null, lastAction: null, renders: 0, renderedAt: null,
  lastStateDir: null, lastNodPrefix: 'unknown', nodTried: [], legacyDir: null,
}

type Painter = Pick<EngineInterface, 'ui'>

/** The same field value: by content, the click-path objects are plain data. */
const same = (a: unknown, b: unknown): boolean => Object.is(a, b) || JSON.stringify(a) === JSON.stringify(b)

/**
 * Changes fields of `local` and asks for a redraw of the pane — only if something changed: every redraw can
 * take the focus off the pane. A refused invalidate does not break the button.
 */
export function setLocal($: Painter, patch: Partial<Local>): void {
  const keys = Object.keys(patch) as (keyof Local)[]
  if (keys.every(k => same(local[k], patch[k]))) return
  Object.assign(local, patch)
  try {
    $.ui.invalidate('ui.render')
  } catch {
    // no redraw — the footer and the status catch up on the next one
  }
}

/**
 * A new session is a clean click state: "saving…", the batch progress, the error and the footer go out. The
 * render counter stays (it is about the module instance); the write lock is in actions.ts, a live write holds it.
 */
export function resetLocal($: Painter): void {
  setLocal($, {
    pending: null, progress: null, writeError: null, lastAction: null, lastStateDir: null, lastNodPrefix: 'unknown',
    nodTried: [], legacyDir: null,
  })
}

/** A drawing: its number and time; no redraw — it is being drawn already. */
export function countRender(at: number): number {
  local.renders += 1
  local.renderedAt = at

  return local.renders
}
