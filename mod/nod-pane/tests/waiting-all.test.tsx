import { test, expect } from 'claude-code/testing'
import { STATE, STATE_FULL, STATE_STALE } from './fixtures'
import { mountPane, runNod, seat, startSession, writeButtons } from './harness'
import type { World } from './harness'
import type { Waiting } from '../hooks/snapshot'

const NOW = Date.parse('2026-10-20T10:12:00')
const world = (state: unknown, extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(state) }, mtime: 1, now: NOW, ...extra })
const decisionRuns = (runs: (readonly string[])[]) => runs.filter(r => r.includes('decision'))
const [FORK, , LAST] = STATE_FULL.waiting as [Waiting, Waiting, Waiting]

for (const surface of ['desktop', 'terminal'] as const) {
  test(`accept all writes the proposed answer of each in order on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'answer-all' }))?.props)
      .toMatchObject({ label: 'Accept all proposed', variant: 'primary', hotkey: 'a' })
    await ui.press({ key: 'answer-all' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs).map(r => r.slice(-2)))
      .toEqual([['d-fork', 'ISO'], ['d-ver2', 'accept'], ['d-ver1', 'accept']])
    expect(decisionRuns(calls.runs).some(r => r.includes('--free'))).toBe(false)
    // one rebuild at the end, not after each decision
    const lastDecision = calls.runs.findLastIndex(r => r.includes('decision'))
    expect(calls.runs.slice(lastDecision + 1).filter(r => r.includes('--peek'))).toHaveLength(1)
    expect(calls.runs.slice(0, lastDecision).filter(r => r.includes('--peek'))).toHaveLength(0)
    expect(calls.runs.at(-1)).toContain('--peek')
    expect(await ui.find({ key: 'busy:all' })).toBeUndefined()
    expect(await ui.find({ key: 'answer-all' })).toBeDefined()
  })

  test(`during the batch "saving N of M…" shows, no write buttons on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, {
      run: async argv => {
        if (argv.includes('decision')) await calls.clock.sleep(1000)

        return {}
      },
    }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'answer-all' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'busy:all' }))?.text).toBe('saving 1 of 3…')
    expect(await writeButtons(ui)).toHaveLength(0)
    await calls.clock.advance(1000)
    await calls.clock.settle()
    expect((await ui.find({ key: 'busy:all' }))?.text).toBe('saving 2 of 3…')
    await calls.clock.advance(1000)
    await calls.clock.settle()
    expect((await ui.find({ key: 'busy:all' }))?.text).toBe('saving 3 of 3…')
    await calls.clock.advance(1000)
    await calls.clock.settle()
    expect(await ui.find({ key: 'busy:all' })).toBeUndefined()
    expect(decisionRuns(calls.runs)).toHaveLength(3)
  })

  test(`a snapshot rebuild in the middle of the batch keeps "saving N of M…" on ${surface}`, async ($, on) => {
    const w = world(STATE_FULL, {
      run: async argv => {
        if (argv.includes('decision')) await calls.clock.sleep(60000)

        return {}
      },
    })
    const calls = seat(on, w)
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'answer-all' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'busy:all' }))?.text).toBe('saving 1 of 3…')
    w.files[STATE] = JSON.stringify({ ...STATE_FULL, waiting: [LAST] })
    w.mtime = 2
    await calls.clock.advance(15000)
    await calls.clock.settle()
    expect((await ui.find({ key: 'zone:waiting:title' }))?.text).toBe('Waiting for you · 1')
    expect((await ui.find({ key: 'busy:all' }))?.text).toBe('saving 1 of 3…')
    expect(await writeButtons(ui)).toHaveLength(0)
  })

  test(`an error on the second — the queue stops, writeError is on it on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, {
      run: argv => (argv.includes('decision') && argv.includes('d-ver2')
        ? { exitCode: 2, stderr: 'error: no decision “d-ver2”\n' }
        : {}),
    }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'answer-all' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toHaveLength(2)
    expect((await ui.find({ key: 'err:d-ver2' }))?.text).toBe('not saved: no decision “d-ver2”')
    expect(await ui.find({ key: 'err:d-fork' })).toBeUndefined()
    expect(await ui.find({ key: 'busy:all' })).toBeUndefined()
    expect(await ui.find({ key: 'retry:d-ver2' })).toBeDefined()
    expect(calls.runs.at(-1)).toContain('--peek')
  })

  test(`no "all" button with one decision on ${surface}`, async ($, on) => {
    const one = seat(on, world({ ...STATE_FULL, waiting: [FORK] }))
    await startSession(one, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'answer-all' })).toBeUndefined()
    expect(await ui.find({ key: 'free:d-fork' })).toBeDefined()
    await ui.unmount()
  })

  test(`no "all" and no "Your own answer" when stale on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_STALE))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'answer-all' })).toBeUndefined()
    expect(await ui.find({ key: 'free:d-fork' })).toBeUndefined()
    expect(await writeButtons(ui)).toHaveLength(0)
  })

  test(`own answer: Input, Enter writes with --free, an empty one is not written, Cancel closes on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'free:d-fork' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'free-input:d-fork' }))?.props)
      .toMatchObject({ label: 'Your own answer', placeholder: 'up to 20 words', submitLabel: 'save' })
    expect(await ui.find({ key: 'opt:d-fork:0' })).toBeUndefined()
    await ui.press({ key: 'free-cancel:d-fork' })
    await calls.clock.settle()
    expect(await ui.find({ key: 'free-input:d-fork' })).toBeUndefined()
    expect(await ui.find({ key: 'opt:d-fork:0' })).toBeDefined()

    await ui.press({ key: 'free:d-fork' })
    await calls.clock.settle()
    await ui.input({ key: 'free-input:d-fork', text: '  ' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toHaveLength(0)
    await ui.input({ key: 'free-input:d-fork', text: 'From the date of signing in to the app' })
    await calls.clock.settle()
    expect(calls.runs.find(r => r.includes('--free')))
      .toEqual(runNod(['decision', 'answer', '--free', '--', 'd-fork', 'From the date of signing in to the app']))
    expect(await ui.find({ key: 'free-input:d-fork' })).toBeUndefined()
  })

  test(`own answer: on a write error the Input stays open on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, {
      run: argv => (argv.includes('decision') ? { exitCode: 2, stderr: 'error: failure\n' } : {}),
    }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'free:d-fork' })
    await ui.input({ key: 'free-input:d-fork', text: 'Mine' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'err:d-fork' }))?.text).toBe('not saved: failure')
    expect(await ui.find({ key: 'free-input:d-fork' })).toBeDefined()
    expect(await ui.find({ key: 'free-cancel:d-fork' })).toBeDefined()
  })
}
