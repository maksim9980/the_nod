// The pane in Russian: the snapshot says `"lang": "ru"`. Without the field, or with an unknown value, it is English.
// Texts before the first snapshot of a session follow the last snapshot in $.state.nod.
import { test, expect } from 'claude-code/testing'
import { LEGACY_DIR } from '../hooks/find'
import type { Snapshot, Waiting } from '../hooks/snapshot'
import { EN, RU } from '../hooks/texts/index'
import { DIR, REVIEW, ROOT, STATE, STATE_FULL } from './fixtures'
import { mountPane, runNod, seat, startSession } from './harness'
import type { World } from './harness'

const NOW = Date.parse('2026-10-20T10:12:00')
const RU_FULL: Snapshot = { ...STATE_FULL, lang: 'ru' }
const world = (state: unknown, extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(state) }, mtime: 1, now: NOW, ...extra })
const decisionRuns = (runs: (readonly string[])[]) => runs.filter(r => r.includes('decision'))
const nodCommand = ($: Parameters<Parameters<typeof test>[1]>[0], args = '') => $.command.run({
  command: 'nod', args, origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 },
} as never) as Promise<{ text?: string }>

const ACTION: Waiting = {
  id: 'd-act', kind: 'owner-action', card: null, card_title: null,
  question: 'Sign in to claude: claude /login', proposed: 'done', options: ['done', 'postpone'],
  reason: '', created: '2026-10-20T09:30:00',
}

test('Russian formats: months, units, decimal comma, plural of steps', () => {
  expect(RU.formatDate('2026-10-17T00:00:00')).toBe('17 окт')
  expect(RU.formatDate('2026-05-01T00:00:00')).toBe('1 мая')
  expect(RU.formatDateTime('2026-10-20T08:00:00')).toBe('20 окт 08:00')
  expect(RU.formatAge('2026-10-20T10:00:00', NOW)).toBe('12 мин')
  expect(RU.formatAge('2026-10-20T09:00:00', NOW)).toBe('1 ч 12 мин')
  expect(RU.formatAge('2026-10-17T10:00:00', NOW)).toBe('3 дн')
  expect(RU.formatTokens(25000000)).toBe('25,0 M')
  expect([1, 2, 5, 11, 21, 22].map(n => RU.stepsTitle(n)))
    .toEqual(['Руками · 1 шаг', 'Руками · 2 шага', 'Руками · 5 шагов', 'Руками · 11 шагов', 'Руками · 21 шаг', 'Руками · 22 шага'])
})

for (const surface of ['desktop', 'terminal'] as const) {
  test(`ru snapshot draws russian zones on ${surface}`, async ($, on) => {
    const calls = seat(on, world(RU_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'zone:waiting:title' }))?.text).toBe('Ждёт тебя · 3')
    expect((await ui.find({ key: 'zone:running:title' }))?.text).toBe('В ране · 1')
    expect((await ui.find({ key: 'zone:since:title' }))?.text).toBe('Пока тебя не было · с 17 окт')
    expect((await ui.find({ key: 'zone:backlog:title' }))?.text).toBe('Бэклог · 44')
    expect((await ui.find({ key: 'zone:review:title' }))?.text).toBe('Обзор недели · —')
    expect((await ui.find({ key: 'header' }))?.text)
      .toMatch(/^proj · laptop · обновлено 12 мин назад · отрисовано \d\d:\d\d:\d\d · #\d+$/)
    expect((await ui.find({ key: 'focus-hint' }))?.text).toBe('первый клик по панели даёт ей фокус, второй — действие')
    expect((await ui.find({ key: 'answer-all' }))?.props).toMatchObject({ label: 'Согласен со всеми предложенными' })
    expect((await ui.find({ key: 'opt:d-fork:0' }))?.props).toMatchObject({ label: 'ISO · предложено' })
    expect((await ui.find({ key: 'res:d-ver2' }))?.text).toBe('Приёмщик: решилась — 3 cards of 3')
    expect((await ui.find({ key: 'backlog:more' }))?.text).toBe('ещё 39')
  })

  test(`missing lang draws english on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'zone:waiting:title' }))?.text).toBe('Waiting for you · 3')
    expect((await ui.find({ key: 'zone:backlog:title' }))?.text).toBe('Backlog · 44')
  })

  test(`an unknown lang draws english on ${surface}`, async ($, on) => {
    const calls = seat(on, world({ ...STATE_FULL, lang: 'de' }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'zone:waiting:title' }))?.text).toBe('Waiting for you · 3')
  })

  test(`owner-action in Russian: Russian labels for done and postpone, sends postpone on ${surface}`, async ($, on) => {
    const calls = seat(on, world({ ...RU_FULL, waiting: [ACTION] }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'label:d-act' }))?.text).toBe('Нужно действие')
    expect((await ui.find({ key: 'opt:d-act:0' }))?.props).toMatchObject({ label: 'Сделано · предложено', variant: 'primary' })
    expect((await ui.find({ key: 'opt:d-act:1' }))?.props).toMatchObject({ label: 'Отложить' })
    await ui.press({ key: 'opt:d-act:1' })
    await calls.clock.settle()
    expect(calls.statuses).toContain('Nod: нажато «Отложить»…')
    expect(calls.statuses.some(s => /^Nod: записано d-act · \d+ мс$/.test(String(s)))).toBe(true)
    expect(decisionRuns(calls.runs)).toEqual([runNod(['decision', 'answer', '--', 'd-act', 'postpone'])])
  })

  test(`the Russian core error prefix is stripped on ${surface}`, async ($, on) => {
    const calls = seat(on, world(RU_FULL, {
      run: argv => (argv.includes('decision') ? { exitCode: 3, stderr: 'ошибка: состояние не свежее\n' } : {}),
    }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-fork:1' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'err:d-fork' }))?.text).toBe('не записано: состояние не свежее')
    expect((await ui.find({ key: 'retry:d-fork' }))?.props).toMatchObject({ label: 'Повторить' })
  })

  test(`a snapshot switching to ru redraws the pane in Russian on ${surface}`, async ($, on) => {
    const w = world(STATE_FULL)
    const calls = seat(on, w)
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'zone:waiting:title' }))?.text).toBe('Waiting for you · 3')
    w.files[STATE] = JSON.stringify(RU_FULL)
    w.mtime = 2
    await calls.clock.advance(15000)
    await calls.clock.settle()
    expect((await ui.find({ key: 'zone:waiting:title' }))?.text).toBe('Ждёт тебя · 3')
  })
}

test('the review prompt names the review section of its language', () => {
  expect(EN.promptApply(REVIEW, DIR)).toContain('section “What to improve”, items 1, 3')
  expect(RU.promptApply(REVIEW, DIR)).toContain('раздел «Что улучшить», пункты 1, 3')
})

test('/nod answers in the snapshot language', async ($, on) => {
  const calls = seat(on, world(RU_FULL))
  await startSession(calls, $)
  const text = (await nodCommand($)).text ?? ''
  expect(text.split('\n')[0]).toBe('Nod: панель открыта · ' + DIR)
  expect(text).toContain('\nвладелец панели: этот экземпляр')
  expect(text).toContain('\nпоследнее действие: —')
  expect((await nodCommand($, 'nonsense')).text).toBe(RU.subUnknown)
})

test('texts before the first snapshot: the language of the last snapshot in $.state.nod, otherwise English', { options: { diag: true } }, async ($, on) => {
  const calls = seat(on, world(RU_FULL))
  await startSession(calls, $)
  // The first session of this $.state: no earlier snapshot — the load line is English.
  expect(calls.transcript.filter(l => l.startsWith('Nod: mod loaded from '))).toHaveLength(1)
  calls.transcript.length = 0
  await startSession(calls, $)
  // The second start finds the Russian snapshot of the previous load.
  expect(calls.transcript.filter(l => l.startsWith('Nod: мод загружен из '))).toHaveLength(1)
  expect(calls.transcript.some(l => l.includes('/nod зарегистрирована, в реестре движка: да (plugin nod)'))).toBe(true)
})

test('the legacy hint in Russian after a Russian snapshot', async ($, on) => {
  const files: Record<string, string> = { [STATE]: JSON.stringify(RU_FULL) }
  const calls = seat(on, { files, mtime: 1, now: NOW })
  await startSession(calls, $)
  // The project is back to the older version's folder: no .nod, only the old state.
  delete files[STATE]
  files[ROOT + '\\' + LEGACY_DIR + '\\state.json'] = '{}'
  await startSession(calls, $)
  expect((await nodCommand($)).text?.split('\n')[0]).toBe(RU.legacyFound)
  const ui = await mountPane($, 'desktop')
  expect((await ui.find({ key: 'legacy' }))?.text).toBe(RU.legacyFound)
})
