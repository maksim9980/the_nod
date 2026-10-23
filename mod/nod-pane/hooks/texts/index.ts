// Texts of the pane in two languages. The language comes from the snapshot's `lang` field (the core writes it
// by `NOD_LANG` or `lang` in harness.toml); without it, or with an unknown value, the pane is English.
// Texts outside a drawing (status lines, /nod answers, log lines) follow the language of the last snapshot
// the mod saw in $.state.nod; before any snapshot they are English.
import { EN } from './en'
import type { Texts } from './en'
import { RU } from './ru'

export { EN, RU }
export type { Texts }
export { LABEL_MAX, clip, formatClock } from './format'

export type Lang = 'en' | 'ru'

/** Language of a snapshot: its `lang` field; missing or unknown — English. */
export function langOf(snapshot: unknown): Lang {
  if (typeof snapshot !== 'object' || snapshot === null) return 'en'

  return (snapshot as { lang?: unknown }).lang === 'ru' ? 'ru' : 'en'
}

export const textsFor = (lang: Lang): Texts => (lang === 'ru' ? RU : EN)

/** Error prefixes of the core's stderr in every language: the pane strips any of them. */
export const ERROR_PREFIXES: readonly string[] = [EN.errorPrefix, RU.errorPrefix]

// The language of the last snapshot the mod saw in $.state.nod. A module variable: a drawing may set it
// (it writes nothing to $.state), and a hot reload starts it over as English until the next read.
let current: Lang = 'en'

/** Takes the language of a snapshot the mod has just read or written; no snapshot — the language stays. */
export function noteLang(snapshot: unknown): void {
  if (typeof snapshot === 'object' && snapshot !== null) current = langOf(snapshot)
}

/** Session start: the language of the previous load's last snapshot, or English without one. */
export function startLang(snapshot: unknown): void {
  current = langOf(snapshot)
}

export const currentLang = (): Lang => current

/** Texts in the current language. */
export const texts = (): Texts => textsFor(current)
