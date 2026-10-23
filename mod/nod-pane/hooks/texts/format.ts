// Language-neutral pieces the dictionaries share: clock time, label clipping, date parts and spans.
// Core timestamps are local and carry no zone: the date parts are cut from the string, not run through
// Date, so that a zone cannot shift the day.

/** Longest button label; a longer option is clipped with «…», the whole value still goes to argv. */
export const LABEL_MAX = 60

const MINUTE_MS = 60000
const SECOND_MS = 1000
const HOUR_MIN = 60
const DAY_MIN = 1440
const MEGA = 1000000
const KILO = 1000

const pad2 = (n: number): string => String(n).padStart(2, '0')

/** Local time HH:MM:SS from epoch milliseconds. */
export function formatClock(ms: number): string {
  const d = new Date(ms)

  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
}

/** A label no longer than LABEL_MAX characters. */
export const clip = (text: string): string => (text.length > LABEL_MAX ? text.slice(0, LABEL_MAX - 1) + '…' : text)

/** Day of the month of a core timestamp `YYYY-MM-DDTHH:MM:SS`. */
export const dayOf = (iso: string): number => Number(iso.slice(8, 10))

/** Month index 0–11 of a core timestamp. */
export const monthOf = (iso: string): number => Number(iso.slice(5, 7)) - 1

/** `HH:MM` of a core timestamp. */
export const timeOf = (iso: string): string => iso.slice(11, 16)

/** Whole seconds in `ms`. */
export const secondsOf = (ms: number): number => Math.round(ms / SECOND_MS)

/** Units of an age in one language: days, hours, minutes. */
export type AgeUnits = { day: string; hour: string; minute: string }

/** Age from `fromIso` to `nowMs`: days, else hours and minutes, else minutes. */
export function formatAgeIn(units: AgeUnits, fromIso: string, nowMs: number): string {
  const minutes = Math.max(0, Math.floor((nowMs - Date.parse(fromIso)) / MINUTE_MS))
  if (minutes >= DAY_MIN) return `${Math.floor(minutes / DAY_MIN)} ${units.day}`
  if (minutes < HOUR_MIN) return `${minutes} ${units.minute}`
  const hours = `${Math.floor(minutes / HOUR_MIN)} ${units.hour}`
  const rest = minutes % HOUR_MIN

  return rest === 0 ? hours : `${hours} ${rest} ${units.minute}`
}

/** Token count: millions with one decimal (the decimal mark of the language), thousands rounded. */
export function formatTokensIn(decimalMark: string, n: number): string {
  if (n >= MEGA) return (n / MEGA).toFixed(1).replace('.', decimalMark) + ' M'
  if (n >= KILO) return Math.round(n / KILO) + ' K'

  return String(n)
}
