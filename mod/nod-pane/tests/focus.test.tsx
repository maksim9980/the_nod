// Pane focus and extra redraws. On desktop the first click on a pane without the keyboard gives it focus, the second
// one is the press; every redraw may drop the focus.
import { test, expect } from 'claude-code/testing'
import { setDiag } from '../hooks/report'
import { noteFocus, onPaneFocus } from '../hooks/focus'
import { setLocal } from '../hooks/local'
import { PANE_PROPS, STATE, STATE_FULL } from './fixtures'
import { mountPane, seat, startSession } from './harness'
import type { World } from './harness'

const NOW = Date.parse('2026-10-20T10:12:00')
const world = (extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1, now: NOW, ...extra })
const HINT = 'the first click on the pane gives it focus, the second one acts'
const GAINED = 'Nod: the pane has focus — a button press will work'

/** Fake `$` for the ui.focus handler: status, transcript and timers go to the journal. */
function fakeEngine(journal: string[], timers: (() => void)[]) {
  return {
    ui: {
      status: (text: string | undefined) => { journal.push('status ' + String(text)) },
      log: (text: string, o?: { to?: string }) => { if (o?.to !== 'debug') journal.push('log ' + text) },
      toast: () => undefined,
      invalidate: () => { journal.push('invalidate') },
    },
    clock: { after: (_: number, fn: () => void) => { timers.push(fn); return { cancel: () => undefined } } },
  }
}

const focusEvent = { component: 'Pane', requestId: 'nod', origin: { kind: 'person' } } as const

test('(a) ui.focus from the owner: the status "the pane has focus…" once, next is always called; the status goes out after 3 s', async () => {
  setDiag(true)  // the transcript and the toast are off by default
  const journal: string[] = []
  const timers: (() => void)[] = []
  const $ = fakeEngine(journal, timers)
  noteFocus($ as never, false)
  let passed = 0
  const next = async () => { passed += 1; return {} }
  await onPaneFocus($ as never, focusEvent as never, next as never)
  await onPaneFocus($ as never, { ...focusEvent, element: 'opt:d-fork:0' } as never, next as never)
  expect(passed).toBe(2)
  expect(journal.filter(x => x === 'status ' + GAINED)).toHaveLength(1)
  expect(journal).toContain('log ' + GAINED)
  for (const fire of timers) fire()
  expect(journal.at(-1)).toBe('status undefined')
})

test('(a) a held ring (deny) does not mark the focus', async () => {
  const journal: string[] = []
  const $ = fakeEngine(journal, [])
  noteFocus($ as never, false)
  await onPaneFocus($ as never, focusEvent as never, (async () => ({ deny: 'holding' })) as never)
  expect(journal.filter(x => x.startsWith('status '))).toEqual([])
})

test('(a) ui.focus from a plugin gives no status but goes on', async () => {
  const journal: string[] = []
  const $ = fakeEngine(journal, [])
  noteFocus($ as never, false)
  let passed = 0
  await onPaneFocus($ as never, { ...focusEvent, origin: { kind: 'plugin', name: 'x' } } as never,
    (async () => { passed += 1; return {} }) as never)
  expect(passed).toBe(1)
  expect(journal.filter(x => x.startsWith('status '))).toEqual([])
})

for (const surface of ['desktop', 'terminal'] as const) {
  test(`(b) the first-click hint — while the pane has no focus; with focus it is gone on ${surface}`, async ($, on) => {
    const calls = seat(on, world())
    await startSession(calls, $)
    const ui = await mountPane($, surface, { ...PANE_PROPS, isFocused: false })
    expect((await ui.find({ key: 'focus-hint' }))?.text).toBe(HINT)
    await ui.redraw({ ...PANE_PROPS, isFocused: true } as never)
    expect(await ui.find({ key: 'focus-hint' })).toBeUndefined()
    await ui.redraw({ ...PANE_PROPS, isFocused: false } as never)
    expect((await ui.find({ key: 'focus-hint' }))?.text).toBe(HINT)
  })

  test(`(a) isFocused false → true in a drawing — one status "the pane has focus…" per change on ${surface}`, { options: { diag: true } }, async ($, on) => {
    const calls = seat(on, world())
    await startSession(calls, $)
    const ui = await mountPane($, surface, { ...PANE_PROPS, isFocused: false })
    const count = () => calls.statuses.filter(s => s === GAINED).length
    expect(count()).toBe(0)
    await ui.redraw({ ...PANE_PROPS, isFocused: true } as never)
    expect(count()).toBe(1)
    await ui.redraw({ ...PANE_PROPS, isFocused: true } as never)
    expect(count()).toBe(1)
    await ui.redraw({ ...PANE_PROPS, isFocused: false } as never)
    await ui.redraw({ ...PANE_PROPS, isFocused: true } as never)
    expect(count()).toBe(2)
    expect(calls.transcript.filter(l => l === GAINED)).toHaveLength(2)
    // The focus status is not a press: /nod does not take it as the "last press".
    const ran = await $.command.run({
      command: 'nod', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 },
    } as never) as { text?: string }
    expect(ran.text).not.toContain('last press: ' + GAINED)
  })
}

test('(c) a timer tick with an unchanged file: neither a $.state write nor an invalidate', async ($, on) => {
  const sets: string[] = []
  on('state.set', (async (_: unknown, e: { key: string }, next: (e: unknown) => Promise<unknown>) => {
    sets.push(e.key)

    return next(e)
  }) as never)
  const calls = seat(on, world())
  await startSession(calls, $)
  await mountPane($, 'desktop')
  await calls.clock.settle()
  const before = { sets: sets.length, invalidates: calls.invalidates.length, stats: calls.stats.length }
  await calls.clock.advance(15000)
  await calls.clock.settle()
  // The tick happened: the file was checked by mtime; it changed no data — neither a write nor a redraw.
  expect(calls.stats.length).toBeGreaterThan(before.stats)
  expect(sets.length).toBe(before.sets)
  expect(calls.invalidates.length).toBe(before.invalidates)
})

test('(c) setLocal with the same value does not call invalidate; with a new one it does', () => {
  const journal: string[] = []
  const $ = fakeEngine(journal, [])
  setLocal($ as never, { progress: { done: 1, total: 3 } })
  const after = journal.length
  setLocal($ as never, { progress: { done: 1, total: 3 }, pending: null, writeError: null })
  expect(journal.length).toBe(after)
  setLocal($ as never, { progress: { done: 2, total: 3 } })
  expect(journal.length).toBe(after + 1)
  setLocal($ as never, { progress: null })
})
