import { test, expect } from 'claude-code/testing'
import { STATE, STATE_FULL } from './fixtures'
import { mountPane, runNod, seat, startSession } from './harness'
import type { Mounted, World } from './harness'
import type { Snapshot, Waiting } from '../hooks/snapshot'

const NOW = Date.parse('2026-10-20T10:12:00')
const world = (state: unknown, extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(state) }, mtime: 1, now: NOW, ...extra })
const decisionRuns = (runs: (readonly string[])[]) => runs.filter(r => r.includes('decision'))

// Created after all decisions of STATE_FULL: by time it would stand last.
const ACTION: Waiting = {
  id: 'd-act', kind: 'owner-action', card: null, card_title: null,
  question: 'Sign in to claude: claude /login', proposed: 'done', options: ['done', 'postpone'],
  reason: '', created: '2026-10-20T09:30:00',
}
const MIXED: Snapshot = { ...STATE_FULL, waiting: [...STATE_FULL.waiting, ACTION] }
const [FORK, VERDICT] = STATE_FULL.waiting as [Waiting, Waiting, Waiting]

/** Ids of the "Waiting for you" cards in drawing order. */
const cardOrder = async (ui: Mounted) =>
  (await ui.findAll({ type: 'Box' })).map(b => String(b.key)).filter(k => k.startsWith('dec:')).map(k => k.slice(4))

for (const surface of ['desktop', 'terminal'] as const) {
  test(`owner-action comes first, the rest keep their order on ${surface}`, async ($, on) => {
    const calls = seat(on, world(MIXED))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await cardOrder(ui)).toEqual(['d-act', 'd-fork', 'd-ver2', 'd-ver1'])
  })

  test(`owner-action: the "Action needed" label above the question, a warning frame, not green on ${surface}`, async ($, on) => {
    const calls = seat(on, world(MIXED))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    const card = await ui.find({ key: 'dec:d-act' })
    expect(card?.props?.borderColor).toBe('warning')
    expect((await ui.find({ key: 'dec:d-fork' }))?.props?.borderColor).toBe('success')
    const label = await ui.find({ key: 'label:d-act' })
    expect(label?.text).toBe('Action needed')
    expect(String(card?.text).indexOf('Action needed')).toBeLessThan(String(card?.text).indexOf('Sign in to claude'))
    // Only an owner-action gets the label: a fork and verdicts do not.
    expect(await ui.find({ key: 'label:d-fork' })).toBeUndefined()
    expect(String((await ui.find({ key: 'dec:d-fork' }))?.text)).not.toContain('Action needed')
  })

  test(`owner-action buttons show labels, send canonical values: "Done" primary with a hotkey, "Postpone" sends postpone on ${surface}`, async ($, on) => {
    const calls = seat(on, world(MIXED))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'opt:d-act:0' }))?.props)
      .toMatchObject({ label: 'Done · proposed', variant: 'primary', hotkey: '1' })
    expect((await ui.find({ key: 'opt:d-act:1' }))?.props).toMatchObject({ label: 'Postpone', variant: 'secondary' })
    expect((await ui.find({ key: 'opt:d-fork:0' }))?.props?.hotkey).toBeUndefined()
    await ui.press({ key: 'opt:d-act:1' })
    await calls.clock.settle()
    expect(calls.statuses).toContain('Nod: pressed “Postpone”…')
    expect(decisionRuns(calls.runs)).toEqual([runNod(['decision', 'answer', '--', 'd-act', 'postpone'])])
  })

  test(`owner-action and a fork write the answer with one nod command, different ids and answers on ${surface}`, async ($, on) => {
    const calls = seat(on, world(MIXED))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-act:0' })
    await calls.clock.settle()
    await ui.press({ key: 'opt:d-fork:1' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toEqual([
      runNod(['decision', 'answer', '--', 'd-act', 'done']),
      runNod(['decision', 'answer', '--', 'd-fork', 'Local format']),
    ])
    expect(calls.runs.at(-1)).toContain('--peek')
  })

  test(`owner-action: on a write error the frame and the label stay, below — "not saved" and "Retry" on ${surface}`, async ($, on) => {
    const calls = seat(on, world(MIXED, {
      run: argv => (argv.includes('decision') ? { exitCode: 3, stderr: 'error: state not fresh\n' } : {}),
    }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-act:0' })
    await calls.clock.settle()
    const card = await ui.find({ key: 'dec:d-act' })
    expect(card?.props?.borderColor).toBe('warning')
    expect((await ui.find({ key: 'label:d-act' }))?.text).toBe('Action needed')
    expect((await ui.find({ key: 'err:d-act' }))?.text).toBe('not saved: state not fresh')
    expect(await ui.find({ key: 'retry:d-act' })).toBeDefined()
    const text = String(card?.text)
    expect(text.indexOf('Action needed')).toBeLessThan(text.indexOf('not saved'))
  })

  test(`"all" does not answer an owner-action: it writes only the fork and the verdict on ${surface}`, async ($, on) => {
    const state: Snapshot = { ...STATE_FULL, waiting: [ACTION, FORK, VERDICT] }
    const calls = seat(on, world(state, {
      run: async argv => {
        if (argv.includes('decision')) await calls.clock.sleep(1000)

        return {}
      },
    }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'answer-all' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'busy:all' }))?.text).toBe('saving 1 of 2…')
    await calls.clock.advance(1000)
    await calls.clock.settle()
    await calls.clock.advance(1000)
    await calls.clock.settle()
    expect(decisionRuns(calls.runs).map(r => r.slice(-2))).toEqual([['d-fork', 'ISO'], ['d-ver2', 'accept']])
  })

  test(`an owner-action and one fork — no "all" button on ${surface}`, async ($, on) => {
    const calls = seat(on, world({ ...STATE_FULL, waiting: [ACTION, FORK] }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'answer-all' })).toBeUndefined()
  })
}
