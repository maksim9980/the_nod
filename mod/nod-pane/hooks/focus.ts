// Pane focus. On desktop the pane holds the keyboard after a click, ctrl+x tab or open({ focus }): the first click
// on a pane without the keyboard goes to the focus and does not reach the button, the second one is the press. The
// mod cannot cancel that (open with focus would take typing and hotkeys away from the prompt), so it shows the moment
// of focus instead.
import type { EngineInterface, UiFocusInput, UiFocusResult } from 'claude-code'

import { sayNotice, tell } from './report'
import { texts } from './texts/index'

type Speaker = Pick<EngineInterface, 'ui' | 'clock'>

/** How long the "the pane has focus" status stays. */
export const FOCUS_STATUS_MS = 3000

// Whether the pane holds the keyboard, by what the mod saw last. A click that gives the pane the keyboard does not
// raise ui.focus from the owner (that comes only while the pane holds the keyboard already), so the main signal is
// the `isFocused` change false → true in a drawing; ui.focus only keeps the flag for moves of the ring inside.
let paneFocused = false

/** One status per change: "the pane has focus…" for 3 s (not sticky) and a transcript line with diag. */
function announce($: Speaker): void {
  paneFocused = true
  const line = texts().focusGained()
  sayNotice($, line, FOCUS_STATUS_MS)
  tell($, line)
}

/**
 * A drawing reports whether the pane holds the keyboard: gaining it gives a status (not a $.state write, allowed
 * while drawing), losing it drops the flag, and the next gain speaks again.
 */
export function noteFocus($: Speaker, isFocused: boolean): void {
  if (isFocused && !paneFocused) announce($)
  else if (!isFocused) paneFocused = false
}

/**
 * The ui.focus hook of our pane. The ring always goes on (`next(e)`); if it moved by the owner's move and the gain is
 * not announced yet — announce it. A held ring (`deny`) does not mark the focus.
 */
export async function onPaneFocus(
  $: Speaker, e: UiFocusInput, next: (e: UiFocusInput) => Promise<UiFocusResult>,
): Promise<UiFocusResult> {
  const moved = await next(e)
  if (moved.deny === undefined && e.origin.kind === 'person' && !paneFocused) announce($)

  return moved
}
