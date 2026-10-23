import { texts } from './texts/index'
import type { Texts } from './texts/index'

// Snapshot types after the_nod/snapshot.py, schema 1.
export type Acceptance = {
  level: 1 | 2 | 3
  result: 'solved' | 'unsolved' | 'unverified'
  evidence: string
  frames: { path: string; caption: string }[]
  steps: string[]
  report: string | null
}

export type Waiting = {
  id: string
  kind: 'brief-yes' | 'fork' | 'verdict' | 'next-batch' | 'return' | 'run-stuck' | 'pain' | 'owner-action'
  card: string | null
  card_title: string | null
  question: string
  proposed: string
  options: string[]
  reason: string
  created: string
  acceptance?: Acceptance | null
}

/** The "all" batch takes decisions with a proposed answer; an owner-action is done by hand, nobody agrees for the owner. */
export const inBatch = (d: Waiting): boolean => d.proposed !== '' && d.kind !== 'owner-action'

export type Running = {
  card: string
  card_title: string
  step: number | null
  step_title: string | null
  run: string | null
  started: string | null
  contracts_done: number
  contracts_total: number
}

export type Since = {
  from: string
  runs: number
  steps_done: number
  accepted: number
  tokens: number
  cards_done: { id: string; title: string; closed_at: string }[]
}

export type BacklogItem = {
  id: string
  title: string
  status: string
  brief: string | null
  steps_total: number
  steps_done: number
}

export type ReviewSuggestion = { n: number; text: string; status: 'proposed' | 'applied' }

/** Last weekly review (core, nod review week); older snapshots have no such key. */
export type Review = {
  week: string
  since: string
  until: string
  runs: number
  steps_done: number
  stops: number
  accepted: number
  tokens: number
  minutes: number
  suggestions: ReviewSuggestion[]
  path: string
}

/** Review suggestions waiting for the owner. */
export const proposed = (r: Review): ReviewSuggestion[] => r.suggestions.filter(s => s.status === 'proposed')

export type Snapshot = {
  schema: 1
  generated_at: string
  host: string
  /** Language of the texts (`en`, `ru`); older snapshots have no such key — English. */
  lang?: string
  fresh: boolean
  stale_since: string | null
  waiting: Waiting[]
  running: Running[]
  since: Since
  backlog: { total: number; top: BacklogItem[] }
  lock: { host: string; at: string } | null
  review?: Review | null
}

const REQUIRED = ['waiting', 'running', 'since', 'backlog'] as const

/** Parses `text` as a schema 1 snapshot; does not throw. Errors are in the language of `t`. */
export function parseSnapshot(text: string, t: Texts = texts()): { snapshot: Snapshot } | { error: string } {
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch (err) {
    return { error: t.notJson(err instanceof Error ? err.message : String(err)) }
  }
  if (typeof data !== 'object' || data === null || Array.isArray(data)) return { error: t.notJson(t.notObject) }
  const obj = data as Record<string, unknown>
  if (obj.schema !== 1) return { error: t.unknownSchema(String(obj.schema)) }
  for (const name of REQUIRED) {
    if (obj[name] === undefined || obj[name] === null) return { error: t.noField(name) }
  }

  const since = obj.since as { from?: unknown; cards_done?: unknown }
  if (typeof since !== 'object' || typeof since.from !== 'string') return { error: t.noField('since.from') }

  const shape = shapeError(obj, since, t)
  if (shape !== null) return { error: shape }

  return { snapshot: obj as unknown as Snapshot }
}

/** Shape of the arrays and numbers: the drawers call filter/map/length and would fail inside ui.render. */
function shapeError(obj: Record<string, unknown>, since: { cards_done?: unknown }, t: Texts): string | null {
  if (!Array.isArray(obj.waiting)) return t.notArray('waiting')
  if (!Array.isArray(obj.running)) return t.notArray('running')
  if (!Array.isArray(since.cards_done)) return t.notArray('since.cards_done')
  const backlog = obj.backlog as { total?: unknown; top?: unknown }
  if (typeof backlog !== 'object' || !Array.isArray(backlog.top)) return t.notArray('backlog.top')
  if (typeof backlog.total !== 'number') return t.notNumber('backlog.total')
  for (const [i, item] of (obj.waiting as unknown[]).entries()) {
    const acc = (item as { acceptance?: unknown } | null)?.acceptance as { frames?: unknown; steps?: unknown } | null | undefined
    if (acc === null || acc === undefined || typeof acc !== 'object') continue
    if (!Array.isArray(acc.frames)) return t.notArray(`waiting[${i}].acceptance.frames`)
    if (!Array.isArray(acc.steps)) return t.notArray(`waiting[${i}].acceptance.steps`)
  }
  // Older snapshots without the review key count as null; fields other than the week and the list are not checked.
  const review = obj.review as { week?: unknown; suggestions?: unknown } | null | undefined
  if (review !== undefined && review !== null) {
    if (typeof review !== 'object' || typeof review.week !== 'string') return t.noField('review.week')
    if (!Array.isArray(review.suggestions)) return t.notArray('review.suggestions')
  }

  return null
}
