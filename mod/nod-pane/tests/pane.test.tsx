import { test, expect } from 'claude-code/testing'
import { DIR, PANE_PROPS, NOD, STATE, STATE_FULL, STATE_NO_BACKLOG, STATE_STALE } from './fixtures'
import { mountPane, seat, startSession, writeButtons } from './harness'
import type { World } from './harness'
import { EN, formatClock } from '../hooks/texts/index'
import { canWrite } from '../hooks/draw/pane'
import type { PaneModel } from '../hooks/draw/pane'

const NOW = Date.parse('2026-10-20T10:12:00')

const world = (state: unknown, extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(state) }, mtime: 1, now: NOW, ...extra })

test('text formats', () => {
  expect(EN.zoneTitle('Waiting for you', 3)).toBe('Waiting for you · 3')
  expect(EN.formatDate('2026-10-17T00:00:00')).toBe('Oct 17')
  expect(EN.formatDate('2026-05-01T00:00:00')).toBe('May 1')
  expect(EN.formatDateTime('2026-10-20T08:00:00')).toBe('Oct 20 08:00')
  expect(EN.staleLine('2026-10-20T08:00:00')).toBe('State not fresh since Oct 20 08:00: writes are off, run git pull first')
  expect(EN.headerLine('proj', 'laptop', '12 min')).toBe('proj · laptop · updated 12 min ago')
  expect(EN.renderedTail(Date.parse('2026-10-20T10:12:05'), 7)).toBe(' · drawn 10:12:05 · #7')
  expect(formatClock(Date.parse('2026-10-20T09:03:04'))).toBe('09:03:04')
  expect(EN.formatAge('2026-10-20T10:00:00', NOW)).toBe('12 min')
  expect(EN.formatAge('2026-10-20T09:00:00', NOW)).toBe('1 h 12 min')
  expect(EN.formatAge('2026-10-20T08:12:00', NOW)).toBe('2 h')
  expect(EN.formatAge('2026-10-17T10:00:00', NOW)).toBe('3 d')
  expect(EN.formatTokens(25000000)).toBe('25.0 M')
  expect(EN.formatTokens(812000)).toBe('812 K')
  expect(EN.formatTokens(730)).toBe('730')
})

test('canWrite: only a fresh state and nod found', () => {
  const base = { snapshot: STATE_FULL, nodMissing: false } as PaneModel
  expect(canWrite(base)).toBe(true)
  expect(canWrite({ ...base, nodMissing: true })).toBe(false)
  expect(canWrite({ ...base, snapshot: STATE_STALE })).toBe(false)
  expect(canWrite({ ...base, snapshot: null })).toBe(false)
})

for (const surface of ['desktop', 'terminal'] as const) {
  test(`zone titles with counts on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'zone:waiting:title' }))?.text).toBe('Waiting for you · 3')
    expect((await ui.find({ key: 'zone:running:title' }))?.text).toBe('In a run · 1')
    expect((await ui.find({ key: 'zone:since:title' }))?.text).toBe('While you were away · since Oct 17')
    expect((await ui.find({ key: 'zone:backlog:title' }))?.text).toBe('Backlog · 44')
    expect((await ui.find({ key: 'zone:review:title' }))?.text).toBe('Weekly review · —')
    expect((await ui.find({ key: 'header' }))?.text)
      .toMatch(/^proj · laptop · updated 12 min ago · drawn \d\d:\d\d:\d\d · #\d+$/)
    expect((await writeButtons(ui)).length).toBeGreaterThan(0)
    expect(await ui.find({ key: 'stale' })).toBeUndefined()
    expect(await ui.find({ key: 'load-error' })).toBeUndefined()
  })

  test(`stale — the first line is a warning, no write buttons on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_STALE))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'stale' }))?.text)
      .toBe('State not fresh since Oct 20 08:00: writes are off, run git pull first')
    expect(await writeButtons(ui)).toHaveLength(0)
    expect(await ui.find({ key: 'dec:d-fork' })).toBeDefined()
    expect((await ui.find({ key: 'zone:waiting:title' }))?.text).toBe('Waiting for you · 3')
  })

  test(`nod not found — a line and no write buttons on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, { run: argv => (argv.at(-1) === '--help' ? { exitCode: 1 } : {}) }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'nod-missing' }))?.text)
      .toBe('nod not found: Python 3.13 is needed in PATH; your own command — /config, field nod.core')
    expect(await ui.find({ key: 'stale' })).toBeUndefined()
    expect(await writeButtons(ui)).toHaveLength(0)
  })

  test(`empty zones with STATE_NO_BACKLOG on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_NO_BACKLOG))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'zone:waiting:empty' }))?.text).toBe('No decisions')
    expect((await ui.find({ key: 'running:empty' }))?.text).toBe('Nothing running')
    expect((await ui.find({ key: 'since:empty' }))?.text).toBe('Quiet')
    expect((await ui.find({ key: 'backlog:empty' }))?.text).toBe('The backlog is empty')
    expect((await ui.find({ key: 'zone:waiting:title' }))?.text).toBe('Waiting for you · 0')
    expect((await ui.find({ key: 'zone:backlog:title' }))?.text).toBe('Backlog · 0')
  })

  test(`a read error — a line, Refresh calls nod status --peek --since on ${surface}`, async ($, on) => {
    const w = world(STATE_FULL)
    const calls = seat(on, w)
    await startSession(calls, $)
    w.files[STATE] = '{'
    w.mtime = 2
    await calls.clock.advance(15000)
    await calls.clock.settle()
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'load-error' }))?.text).toMatch(/^D:\\x\\proj\\\.nod\\state\.json: not JSON/)
    expect((await ui.find({ key: 'zone:waiting:title' }))?.text).toBe('Waiting for you · 3')
    await ui.press({ key: 'refresh' })
    await calls.clock.settle()
    expect(calls.runs.at(-1)).toEqual([...NOD, '--root', DIR, 'status', '--peek', '--since', '2026-10-17T00:00:00'])
  })

  test(`no snapshot, an error — the error line and Refresh, no zones on ${surface}`, async ($, on) => {
    const calls = seat(on, world({ ...STATE_FULL, schema: 2 }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'load-error' }))?.text).toBe(STATE + ': schema 2, the mod knows 1')
    expect(await ui.find({ key: 'refresh' })).toBeDefined()
    expect(await ui.find({ key: 'zone:waiting:title' })).toBeUndefined()
  })

  test(`a narrow pane of 40 columns draws on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface, { ...PANE_PROPS, bodyColumns: 40 })
    expect((await ui.find({ key: 'zone:waiting:title' }))?.text).toBe('Waiting for you · 3')
    expect((await ui.find({ key: 'header' }))?.text)
      .toMatch(/^proj · laptop · updated 12 min ago · drawn \d\d:\d\d:\d\d · #\d+$/)
  })
}
