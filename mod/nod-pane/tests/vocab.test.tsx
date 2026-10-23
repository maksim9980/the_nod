// Canonical state values (the_nod/vocab.py): a button sends the English identifier, its label is in the pane's language.
import { test, expect } from 'claude-code/testing'
import { STATE, STATE_FULL } from './fixtures'
import { mountPane, runNod, seat, startSession } from './harness'
import type { World } from './harness'
import type { Acceptance, Snapshot, Waiting } from '../hooks/snapshot'
import { EN, RU } from '../hooks/texts/index'

const NOW = Date.parse('2026-10-20T10:12:00')
const world = (state: unknown, extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(state) }, mtime: 1, now: NOW, ...extra })
const decisionRuns = (runs: (readonly string[])[]) => runs.filter(r => r.includes('decision'))

const decision = (over: Partial<Waiting>): Waiting => ({
  id: 'd-x', kind: 'fork', card: null, card_title: null, question: 'Q', proposed: '', options: [],
  reason: '', created: '2026-10-20T09:30:00', ...over,
})
const BATCH = decision({
  id: 'd-batch', kind: 'next-batch', question: 'Start the next batch: 3 cards?', proposed: 'yes', options: ['yes', 'no'],
})
const PAIN = decision({ id: 'd-pain', kind: 'pain', question: 'The backlog is empty. What hurts?', proposed: 'wait', options: ['wait'] })
const ACTION = decision({
  id: 'd-act', kind: 'owner-action', question: 'Sign in to claude', proposed: 'done', options: ['done', 'postpone'],
})
const STUCK = decision({
  id: 'd-stuck', kind: 'run-stuck', question: 'The run hung: Export habits to CSV', proposed: 'restart', options: ['restart', 'backlog'],
})
const FORK_NO = decision({ id: 'd-fork-no', kind: 'fork', question: 'Keep the history?', proposed: 'no', options: ['yes', 'no'] })

const only = (waiting: Waiting[]): Snapshot => ({ ...STATE_FULL, waiting })

/** STATE_FULL where d-ver2 has the acceptance result `result`. */
const withResult = (result: Acceptance['result']): Snapshot => ({
  ...STATE_FULL,
  waiting: STATE_FULL.waiting.map(w => (w.id === 'd-ver2' && w.acceptance ? { ...w, acceptance: { ...w.acceptance, result } } : w)),
})
const resultColor = async (ui: { findAll(q: { type: string }): Promise<{ text?: string; props: Record<string, unknown> }[]> }, start: string) =>
  (await ui.findAll({ type: 'Text' })).find(t => t.text?.startsWith(start) === true)?.props.color

test('answerLabel: a caption per canonical value, any other value as is', () => {
  const values = ['done', 'postpone', 'yes', 'no', 'wait', 'accept', 'return', 'rerun', 'backlog', 'restart']
  expect(values.map(v => EN.answerLabel(v)))
    .toEqual(['Done', 'Postpone', 'Yes', 'No', 'Wait', 'Accept', 'Return', 'Rerun', 'To backlog', 'Restart'])
  expect(values.map(v => RU.answerLabel(v)))
    .toEqual(['Сделано', 'Отложить', 'Да', 'Нет', 'Подождать', 'Принять', 'Вернуть', 'Перезапустить', 'В бэклог', 'Начать заново'])
  expect(EN.answerLabel('Local format')).toBe('Local format')
  expect(RU.answerLabel('ISO')).toBe('ISO')
})

test('result and review status captions by canonical value; an unknown one as is', () => {
  expect(['solved', 'unsolved', 'unverified', 'other'].map(v => EN.resultLabel(v)))
    .toEqual(['solved', 'not solved', 'not verified', 'other'])
  expect(['solved', 'unsolved', 'unverified'].map(v => RU.resultLabel(v))).toEqual(['решилась', 'не решилась', 'не проверено'])
  expect(['proposed', 'applied', 'other'].map(v => EN.suggestionStatus(v))).toEqual(['proposed', 'applied', 'other'])
  expect(['proposed', 'applied'].map(v => RU.suggestionStatus(v))).toEqual(['предлагается', 'внесено'])
})

for (const surface of ['desktop', 'terminal'] as const) {
  test(`owner-action buttons show labels, send canonical values on ${surface}`, async ($, on) => {
    const calls = seat(on, world(only([ACTION])))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'opt:d-act:0' }))?.props).toMatchObject({ label: 'Done · proposed', variant: 'primary' })
    expect((await ui.find({ key: 'opt:d-act:1' }))?.props).toMatchObject({ label: 'Postpone', variant: 'secondary' })
    await ui.press({ key: 'opt:d-act:1' })
    await calls.clock.settle()
    expect(calls.statuses).toContain('Nod: pressed “Postpone”…')
    expect(decisionRuns(calls.runs)).toEqual([runNod(['decision', 'answer', '--', 'd-act', 'postpone'])])
  })

  for (const [result, color, label] of [
    ['solved', 'success', 'solved'], ['unsolved', 'error', 'not solved'], ['unverified', 'warning', 'not verified'],
  ] as const) {
    test(`acceptance colors by canonical result: ${result} on ${surface}`, async ($, on) => {
      const calls = seat(on, world(withResult(result)))
      await startSession(calls, $)
      const ui = await mountPane($, surface)
      expect((await ui.find({ key: 'res:d-ver2' }))?.text).toBe('Acceptance: ' + label + ' — 3 cards of 3')
      expect(await resultColor(ui, 'Acceptance: ' + label)).toBe(color)
    })
  }

  test(`next-batch: labels "Yes"/"No", yes and no go to the core on ${surface}`, async ($, on) => {
    const calls = seat(on, world(only([BATCH])))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'opt:d-batch:0' }))?.props).toMatchObject({ label: 'Yes · proposed', variant: 'primary' })
    expect((await ui.find({ key: 'opt:d-batch:1' }))?.props).toMatchObject({ label: 'No', variant: 'secondary' })
    await ui.press({ key: 'opt:d-batch:1' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toEqual([runNod(['decision', 'answer', '--', 'd-batch', 'no'])])
  })

  test(`pain: the label "Wait", wait goes to the core on ${surface}`, async ($, on) => {
    const calls = seat(on, world(only([PAIN])))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'opt:d-pain:0' }))?.props).toMatchObject({ label: 'Wait · proposed' })
    await ui.press({ key: 'opt:d-pain:0' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toEqual([runNod(['decision', 'answer', '--', 'd-pain', 'wait'])])
  })

  test(`run-stuck: labels "Restart"/"To backlog", backlog goes to the core on ${surface}`, async ($, on) => {
    const calls = seat(on, world(only([STUCK])))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'opt:d-stuck:0' }))?.props).toMatchObject({ label: 'Restart · proposed' })
    expect((await ui.find({ key: 'opt:d-stuck:1' }))?.props).toMatchObject({ label: 'To backlog' })
    await ui.press({ key: 'opt:d-stuck:1' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toEqual([runNod(['decision', 'answer', '--', 'd-stuck', 'backlog'])])
  })

  test(`a fork with options yes/no shows them as is on ${surface}`, async ($, on) => {
    const calls = seat(on, world(only([FORK_NO])))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'opt:d-fork-no:0' }))?.props).toMatchObject({ label: 'yes' })
    expect((await ui.find({ key: 'opt:d-fork-no:1' }))?.props).toMatchObject({ label: 'no · proposed' })
  })

  test(`"all" sends the proposed values as is: yes for the batch on ${surface}`, async ($, on) => {
    const calls = seat(on, world(only([BATCH, FORK_NO])))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'answer-all' })
    await calls.clock.settle()
    await calls.clock.settle()
    expect(decisionRuns(calls.runs).map(r => r.slice(-2))).toEqual([['d-batch', 'yes'], ['d-fork-no', 'no']])
  })
}
