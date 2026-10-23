// Self-diagnosis without logs: the status line under the prompt, a transcript line, a toast and the "last action"
// in the pane footer. Status, transcript and toast are synchronous engine calls that depend neither on $.state
// nor on a redraw of the pane; lastAction is a module variable (local.ts), the footer draws it when it is not null.
// The transcript and the toast speak only with `userConfig.diag: true` (off by default); the status and the footer stay.
import type { EngineInterface } from 'claude-code'

import { setLocal } from './local'
import { span, stamp } from './log'
import { safeWrite } from './state'
import type { Cell, LastAction } from './state'
import { texts } from './texts/index'

/** How long the status line stays after a success; an error and a skip stay until the next press. */
export const STATUS_CLEAR_MS = 5000

export type Timer = ReturnType<EngineInterface['clock']['after']>

type Speaker = Pick<EngineInterface, 'ui'>
type Clocked = Pick<EngineInterface, 'ui' | 'clock'>

/** Outcome of a write or an action: ok or the reason; `ignored` — a skip (the guarded body refused to write). */
export type Result = { ok: true } | { ok: false; message: string; ignored?: boolean }

export const OK: Result = { ok: true }

// Timer that clears the status line after a success; a new line cancels it.
let clearTimer: Timer | null = null
// Number of the last press. A sticky line (error, skip, pane state refusal) stays until the next press:
// only lines of the same press replace it, lines of older actions do not.
let gen = 0
let sticky = false
// Last line shown: /nod gives it without atoms (the pane state may not answer).
let lastShown: string | null = null
// Transcript and toast of presses: register sets it from userConfig.diag on every module load.
let diag = false

/** Turns the transcript and the toast of presses on or off (the status and the footer stay). */
export function setDiag(on: boolean): void {
  diag = on
}

/** A visible transcript line; with diag: false or an engine refusal — silently. */
export function tell($: Speaker, text: string): void {
  if (!diag) return
  try {
    $.ui.log(text)
  } catch {
    // no transcript — the status and the footer stay
  }
}

/** A toast; with diag: false or an engine refusal — silently. */
function pop($: Speaker, text: string): void {
  if (!diag) return
  try {
    $.ui.toast(text)
  } catch {
    // no toast — the status and the footer stay
  }
}

/** The last status line the mod showed; null — no presses yet. */
export function lastStatus(): string | null {
  return lastShown
}

/** Cancels a timer; a fired one or one the engine did not give — silently. */
export function cancel(timer: Timer | null): void {
  if (timer === null) return
  try {
    timer.cancel()
  } catch {
    // the timer has fired or the engine did not give it
  }
}

/** The status line as is; an engine refusal does not break the button. */
function show($: Speaker, text: string | undefined, record = true): void {
  try {
    $.ui.status(text)
  } catch {
    // no status — the footer stays
  }
  // "last press" in /nod holds only lines of presses and their outcomes, not pane messages (focus).
  if (text !== undefined && record) lastShown = text
  cancel(clearTimer)
  clearTimer = null
}

/**
 * An action since its start: the number of its press, `notes` — what happened on the way (into the outcome's
 * detail), `keep` — keep the outcome, `told` — which targets the transcript has been told about (not repeated).
 */
export type Track = { what: string; at: number; gen: number; notes: string[]; keep: boolean; told: string[] }

export const track = (what: string): Track => ({ what, at: stamp(), gen, notes: [], keep: false, told: [] })

/** Whether a line of this action may replace the one on screen. */
const mayShow = (t?: Track): boolean => !sticky || (t !== undefined && t.gen === gen)

/**
 * A press goes to three channels at once: status, transcript, toast; each in its own try/catch, not one await and
 * not one $.state call. The first statement of every write handler. A new press drops the stickiness:
 * an error and a skip stay exactly until it.
 */
export function press($: Speaker, label: string): void {
  const t = texts()
  show($, t.pressedStatus(label))
  tell($, t.pressedLog(label, stamp()))
  pop($, t.pressedToast(label))
  gen += 1
  sticky = false
}

/** A line along the action; does not replace a sticky line of another press. */
export function say($: Speaker, text: string | undefined, t?: Track): void {
  if (mayShow(t)) show($, text)
}

/** A sticky line: error, skip, pane state refusal — stays until the next press. */
export function sayStuck($: Speaker, text: string, t?: Track): void {
  if (t !== undefined && !mayShow(t)) return
  show($, text)
  sticky = true
}

/**
 * A pane message not tied to a press (focus): not sticky, goes out after `ms`, does not replace a sticky line
 * and does not get into the "last press" of /nod.
 */
export function sayNotice($: Clocked, text: string, ms: number): void {
  if (sticky) return
  show($, text, false)
  try {
    const timer: Timer = $.clock.after(ms, () => {
      if (clearTimer !== timer || sticky) return
      show($, undefined)
    })
    clearTimer = timer
  } catch {
    // no clock — the line stays until the next press
  }
}

/**
 * A success line: cleared after `clearMs` (STATUS_CLEAR_MS); stays for an action with a pane state refusal.
 * Without `t` it does not replace a sticky line (error, skip).
 */
export function sayDone($: Clocked, text: string, t?: Track, clearMs: number = STATUS_CLEAR_MS): void {
  if (!mayShow(t)) return
  if (t?.keep === true) return sayStuck($, text, t)
  show($, text)
  sticky = false
  try {
    const timer: Timer = $.clock.after(clearMs, () => {
      if (clearTimer !== timer || sticky) return
      show($, undefined)
    })
    clearTimer = timer
  } catch {
    // no clock — the line stays until the next press
  }
}

/**
 * The pane state did not answer a write: a sticky line "… — going on" and a note in the action's outcome.
 * Writing the answer goes on: the click path does not depend on atoms.
 */
export function panelFailed($: Speaker, t: Track, label: string, error: string): void {
  const words = texts()
  const text = words.panelStuck(label, error)
  if (t.notes.includes(text)) return
  t.notes.push(text)
  t.keep = true
  sayStuck($, words.statusLine(words.goingOn(text)), t)
  tell($, words.statusLine(words.goingOn(text)))
}

/** An atom write from the click path: bounded in time, does not throw; a refusal — panelFailed. true — written. */
export async function put<T>($: Clocked, t: Track, cell: Cell<T>, value: T, label: string): Promise<boolean> {
  const r = await safeWrite($, cell, value)
  if (!r.ok) panelFailed($, t, label, r.error ?? '')

  return r.ok
}

/** Writes lastAction into the module: synchronously, $.state is not touched. */
function note($: Speaker, value: LastAction): void {
  setLocal($, { lastAction: value })
}

/**
 * A skipped press — the only early exit of the handlers: status, transcript, toast and lastAction with the reason.
 * A button never exits silently.
 */
export async function ignored($: Clocked, what: string, reason: string): Promise<void> {
  const text = texts().ignoredStatus(reason)
  sayStuck($, text)
  tell($, text)
  pop($, text)
  note($, { what, at: stamp(), ms: null, result: 'ignored', detail: reason })
}

/** The outcome to the transcript (once per action target), an error also as a toast. */
function told($: Speaker, t: Track, key: string, text: string, failed: boolean): void {
  if (t.told.includes(key)) return
  t.told.push(key)
  tell($, text)
  if (failed) pop($, text)
}

/** lastAction "running" with the notes of the way. */
export async function running($: Clocked, t: Track): Promise<void> {
  note($, { what: t.what, at: t.at, ms: null, result: 'running', detail: t.notes.join(' · ') })
}

/** The line of a write outcome (`target` — an id, "all (N)"), without atoms: set as soon as nod returned. */
export function sayResult($: Clocked, t: Track, r: Result, target: string): void {
  const words = texts()
  const ms = span(t.at, stamp())
  const text = r.ok ? words.wroteStatus(target, ms) : words.failedStatus(target, r.message)
  if (r.ok) sayDone($, text, t)
  else sayStuck($, text, t)
  told($, t, target, text, !r.ok)
}

/**
 * The outcome of an action: status and lastAction with the duration. `target` — what was written (an id,
 * "all (N)"): then the line "saved …" / "not saved …"; without it — "<action> — done / error".
 */
export async function finish($: Clocked, t: Track, r: Result, target?: string): Promise<void> {
  const words = texts()
  const ms = span(t.at, stamp())
  if (target !== undefined) sayResult($, t, r, target)
  else if (r.ok) sayDone($, words.doneStatus(t.what, ms), t)
  else sayStuck($, words.errorStatus(t.what, r.message), t)
  if (target === undefined) {
    told($, t, t.what, r.ok ? words.doneStatus(t.what, ms) : words.errorStatus(t.what, r.message), !r.ok)
  }
  await record($, t, r)
}

/**
 * The outcome into lastAction without a status line. Notes of the way ("reset a stuck lock", "… in 70 s, saving",
 * "pane state does not respond") go into the detail on an error too: first, then the reason.
 */
export async function record($: Clocked, t: Track, r: Result): Promise<void> {
  const detail = [...t.notes, ...(r.ok ? [] : [r.message])].join(' · ')
  note($, { what: t.what, at: t.at, ms: span(t.at, stamp()), result: r.ok ? 'ok' : 'error', detail })
}
