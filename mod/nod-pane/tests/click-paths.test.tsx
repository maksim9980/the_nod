// "Clicked — nothing happened" scenarios: each test checks one hypothesis about the cause.
import { test, expect } from 'claude-code/testing'
import { STATE, STATE_FULL } from './fixtures'
import { mountPane, runNod, seat, startSession } from './harness'
import type { World } from './harness'

const NOW = Date.parse('2026-10-20T10:12:00')

const world = (state: unknown, extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(state) }, mtime: 1, now: NOW, ...extra })

const decisionRuns = (runs: (readonly string[])[]) => runs.filter(r => r.includes('decision'))

const ANSWER = runNod(['decision', 'answer', '--', 'd-fork', 'ISO'])

for (const surface of ['desktop', 'terminal'] as const) {
  test(`(a) a fresh driver.lock of this host does not block a write and draws no lock line on ${surface}`, async ($, on) => {
    const own = { ...STATE_FULL, lock: { host: 'laptop', at: '2026-10-20T10:11:00' } }
    const calls = seat(on, world(own))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'lock' })).toBeUndefined()
    await ui.press({ key: 'opt:d-fork:0' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toEqual([ANSWER])
  })

  test(`(c) a click after a second session.start (reload) writes on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-fork:0' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toEqual([ANSWER])
  })

  test(`a click on a tree the timer redrew after a snapshot change writes on ${surface}`, async ($, on) => {
    const w = world(STATE_FULL)
    const calls = seat(on, w)
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    w.files[STATE] = JSON.stringify({ ...STATE_FULL, generated_at: '2026-10-20T10:11:00' })
    w.mtime = 2
    await calls.clock.advance(15000)
    await calls.clock.settle()
    await ui.press({ key: 'opt:d-fork:0' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toEqual([ANSWER])
  })
}
