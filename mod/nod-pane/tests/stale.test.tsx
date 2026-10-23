// Leftover state: $.state survives a hot reload of the module, and a new session.start finds the keys of the
// previous load. The test's state.get hook gives them out until the mod writes the key itself — that is how a host
// store with old values behaves.
import { test, expect } from 'claude-code/testing'
import { STATE, STATE_FULL } from './fixtures'
import { mountPane, runNod, seat, startSession } from './harness'
import type { World } from './harness'

const NOW = Date.parse('2026-10-20T10:12:00')
const world = (extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1, now: NOW, ...extra })
const OTHER = 'C:\\Users\\owner\\.claude\\dev-mods\\0a1b2c3d\\nod-pane'

type StateEvent = { key: string; value?: unknown }
/** The answer of the state.get op event — an envelope `{ value: StateRead }`. */
type Next = (e: StateEvent) => Promise<{ value?: { value?: unknown; version?: number } }>

/** Keys that are reset and their initial values; draft is not reset, instance is written with a new token at once. */
const RESET: Record<string, unknown> = {
  stateDir: null, panePlaced: false, nodPrefix: 'unknown', snapshot: null, loadError: null, lastMtime: 0,
  sinceFrom: null, expanded: [], freeFor: null, otherRoot: null,
}

/** A store with old values over the real one: a key gives the old value until it is overwritten. */
function staleStore(on: Parameters<Parameters<typeof test>[1]>[1]) {
  const stale = new Map<string, unknown>()
  const sets: [string, unknown][] = []
  on('state.get', (async (_: unknown, e: StateEvent, next: Next) => {
    const real = await next(e)

    return stale.has(e.key) ? { ...real, value: { ...real.value, value: stale.get(e.key) } } : real
  }) as never)
  on('state.set', (async (_: unknown, e: StateEvent, next: Next) => {
    sets.push([e.key, e.value])
    stale.delete(e.key)

    return next(e)
  }) as never)

  return { stale, sets }
}

const rootOfToken = (token: unknown): string => String(token).slice(String(token).indexOf('@') + 1)

for (const surface of ['desktop', 'terminal'] as const) {
  test(`(a) old keys of a previous load: session.start resets them, draft stays, a click writes on ${surface}`, async ($, on) => {
    const store = staleStore(on)
    const calls = seat(on, world())
    await startSession(calls, $)
    const root = rootOfToken(store.sets.filter(([k, v]) => k === 'instance' && v !== null).at(-1)?.[1])
    // The previous load left: a foreign token of the same root, a second root, an open field, an error, a draft.
    for (const [k, v] of Object.entries({
      instance: 'old@' + root, otherRoot: OTHER, freeFor: 'd-fork', expanded: ['d-ver2'], loadError: 'an old error',
      lastMtime: 99, sinceFrom: '2026-01-01T00:00:00', panePlaced: true, draft: 'an old draft',
    })) store.stale.set(k, v)
    store.sets.length = 0
    calls.transcript.length = 0
    await startSession(calls, $)
    for (const [key, initial] of Object.entries(RESET)) {
      expect(store.sets.some(([k, v]) => k === key && JSON.stringify(v) === JSON.stringify(initial))).toBe(true)
    }
    expect(store.sets.some(([k]) => k === 'draft')).toBe(false)
    const token = store.sets.filter(([k, v]) => k === 'instance' && v !== null).at(-1)?.[1]
    expect(String(token)).toMatch(/^[0-9a-z]+@/)
    expect(rootOfToken(token)).toBe(root)
    expect(calls.transcript.filter(l => l.startsWith('Nod: mod loaded from ')))
      .toEqual([`Nod: mod loaded from ${root} · instance ${String(token).split('@')[0]} · state reset · /nod registered, in the engine registry: yes (plugin nod)`])
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'free-input:d-fork' })).toBeUndefined()
    expect(await ui.find({ key: 'double-load' })).toBeUndefined()
    expect(await ui.find({ key: 'load-error' })).toBeUndefined()
    expect((await ui.find({ key: 'draft' }))?.text).toBe('an old draft')
    await ui.press({ key: 'opt:d-fork:1' })
    await calls.clock.settle()
    expect(calls.runs.filter(r => r.includes('decision'))).toEqual([runNod(['decision', 'answer', '--', 'd-fork', 'Local format'])])
    expect(calls.statuses).toContain('Nod: pressed “Local format”…')
    expect(calls.transcript.some(l => l.startsWith('Nod: pressed “Local format”'))).toBe(true)
  })
}

test('the reset failed for a key — a transcript line names the key, the start goes on', async ($, on) => {
  let deny = false
  on('state.set', (async (_: unknown, e: StateEvent, next: Next) =>
    (deny && e.key === 'freeFor' ? { deny: 'forbidden' } : next(e))) as never)
  const calls = seat(on, world())
  await startSession(calls, $)
  deny = true
  calls.transcript.length = 0
  await startSession(calls, $)
  expect(calls.transcript.filter(l => l.startsWith('Nod: mod loaded from '))).toHaveLength(1)
  expect(calls.transcript.find(l => l.startsWith('Nod: mod loaded from ')))
    .toMatch(/ · state reset incompletely: freeFor \(.*forbidden.*\) · \/nod registered, in the engine registry: yes \(plugin nod\)$/)
  const ui = await mountPane($, 'desktop')
  expect(await ui.find({ key: 'dec:d-fork' })).toBeDefined()
})
