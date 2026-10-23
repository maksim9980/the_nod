import { test, expect } from 'claude-code/testing'
import { STATE, STATE_FULL, STATE_LOCKED, STATE_NO_BACKLOG } from './fixtures'
import { mountPane, seat, startSession } from './harness'
import type { World } from './harness'
import type { Running } from '../hooks/snapshot'
import { EN } from '../hooks/texts/index'

const NOW = Date.parse('2026-10-20T10:12:00')

const world = (state: unknown): World => ({ files: { [STATE]: JSON.stringify(state) }, mtime: 1, now: NOW })

test('zone texts: the lock and the counters', () => {
  expect(EN.lockLine('desktop', '2026-10-20T09:00:00')).toBe('work in progress on desktop since Oct 20 09:00')
  expect(EN.countersLine(STATE_FULL.since)).toBe('runs 5 · steps 5 · accepted 5 · tokens 25.0 M')
  expect(EN.countersLine({ ...STATE_FULL.since, runs: 0, tokens: 0 })).toBe('runs 0 · steps 5 · accepted 5 · tokens 0')
})

for (const surface of ['desktop', 'terminal'] as const) {
  test(`in a run: step, contracts, age on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    const text = (await ui.find({ key: 'run:c-aaaa' }))?.text
    expect(text).toContain('step 2: Step 2')
    expect(text).toContain('contracts 2/5 · running 1 h 12 min')
    expect(await ui.find({ key: 'running:empty' })).toBeUndefined()
    expect(await ui.find({ key: 'lock' })).toBeUndefined()
  })

  test(`a run not started and without a start time on ${surface}`, async ($, on) => {
    const idle = { ...(STATE_FULL.running[0] as Running), step: null, step_title: null, started: null }
    const calls = seat(on, world({ ...STATE_FULL, running: [idle] }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    const text = (await ui.find({ key: 'run:c-aaaa' }))?.text
    expect(text).toContain('run not started')
    expect(text).toContain('contracts 2/5')
    expect(text).not.toContain('running')
  })

  test(`a lock of another machine — a warning line on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_LOCKED))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'lock' }))?.text).toBe('work in progress on desktop since Oct 20 09:00')
    expect(await ui.find({ key: 'run:c-aaaa' })).toBeDefined()
  })

  test(`a lock of this machine — no line on ${surface}`, async ($, on) => {
    const same = { ...STATE_LOCKED, lock: { host: 'laptop', at: '2026-10-20T09:00:00' } }
    const calls = seat(on, world(same))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'lock' })).toBeUndefined()
  })

  test(`a lock of another machine with an empty run — the line and "Nothing running" on ${surface}`, async ($, on) => {
    const calls = seat(on, world({ ...STATE_LOCKED, running: [] }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'lock' }))?.text).toBe('work in progress on desktop since Oct 20 09:00')
    expect((await ui.find({ key: 'running:empty' }))?.text).toBe('Nothing running')
  })

  test(`while you were away: counters and closed cards on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'since:counters' }))?.text).toBe('runs 5 · steps 5 · accepted 5 · tokens 25.0 M')
    for (const c of STATE_FULL.since.cards_done) expect(await ui.find({ key: 'done:' + c.id })).toBeDefined()
    expect((await ui.find({ key: 'done:c-1001' }))?.text).toBe('Show the day streak in the profile · Oct 18')
    expect(await ui.find({ key: 'since:more' })).toBeUndefined()
    expect(await ui.find({ key: 'since:empty' })).toBeUndefined()
  })

  test(`20 closed — 10 shown and "10 more" on ${surface}`, async ($, on) => {
    const many = Array.from({ length: 20 }, (_, i) => ({
      id: 'c-' + (3000 + i), title: 'Card ' + i, closed_at: '2026-10-19T12:00:00',
    }))
    const calls = seat(on, world({ ...STATE_FULL, since: { ...STATE_FULL.since, cards_done: many } }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'done:c-3009' })).toBeDefined()
    expect(await ui.find({ key: 'done:c-3010' })).toBeUndefined()
    expect((await ui.find({ key: 'since:more' }))?.text).toBe('10 more')
  })

  test(`empty zones — Nothing running and Quiet on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_NO_BACKLOG))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'running:empty' }))?.text).toBe('Nothing running')
    expect((await ui.find({ key: 'since:empty' }))?.text).toBe('Quiet')
    expect(await ui.find({ key: 'since:counters' })).toBeUndefined()
  })

  test(`only closed cards without counters — not "Quiet" on ${surface}`, async ($, on) => {
    const quiet = { ...STATE_NO_BACKLOG.since, cards_done: STATE_FULL.since.cards_done.slice(0, 1) }
    const calls = seat(on, world({ ...STATE_NO_BACKLOG, since: quiet }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'since:empty' })).toBeUndefined()
    expect((await ui.find({ key: 'since:counters' }))?.text).toBe('runs 0 · steps 0 · accepted 0 · tokens 0')
  })
}
