// Protection against a double load. The kit does not start a second mod instance: the pure decisions are checked
// here, and a foreign token comes from a state.get hook.
import { test, expect } from 'claude-code/testing'
import { doubleLoad, isOwner, roleOf, rootOf, tokenOf, viewOf } from '../hooks/owner'
import { EN } from '../hooks/texts/index'
import { STATE, STATE_FULL } from './fixtures'
import { mountPane, seat, startSession } from './harness'

const A = 'C:\\work\\tidepool\\mod\\nod-pane'
const B = 'C:\\Users\\owner\\.claude\\dev-mods\\0a1b2c3d\\nod-pane'

test('(g) isOwner: an empty atom and my token — owner, a foreign one — not', () => {
  expect(isOwner(null, 'abc')).toBe(true)
  expect(isOwner(tokenOf('abc', A), 'abc')).toBe(true)
  expect(isOwner(tokenOf('xyz', A), 'abc')).toBe(false)
  // The foreign token's prefix matches my id: without "@" it would be a false owner.
  expect(isOwner(tokenOf('abcd', A), 'abc')).toBe(false)
})

test('rootOf: the root after the first "@", an "@" in the root is fine', () => {
  expect(rootOf(tokenOf('abc', A))).toBe(A)
  expect(rootOf(tokenOf('abc', 'D:\\a@b'))).toBe('D:\\a@b')
})

test('roleOf (background work): mine — draw; a foreign token of my folder — claim; of another folder — pass', () => {
  expect(roleOf(null, 'abc', A)).toBe('draw')
  expect(roleOf(tokenOf('abc', A), 'abc', A)).toBe('draw')
  expect(roleOf(tokenOf('old', A), 'abc', A)).toBe('claim')
  expect(roleOf(tokenOf('xyz', B), 'abc', A)).toBe('pass')
})

test('doubleLoad: a line only with a second root different from mine', () => {
  expect(doubleLoad(A, null, EN)).toBeNull()
  expect(doubleLoad(A, A, EN)).toBeNull()
  expect(doubleLoad(A, B, EN))
    .toBe(`the mod is loaded twice: ${A} and ${B} — keep one (env CLAUDE_CODE_PLUGIN_DIRS or dev-mods)`)
})

test('viewOf: my, an empty and an unread token — drawn without lines', () => {
  for (const owner of [{ ok: true, value: null }, { ok: true, value: tokenOf('abc', A) }, { ok: false, error: 'timeout 2 s' }] as const) {
    expect(viewOf(owner, 'abc', A)).toEqual({ stale: null, foreignRoot: null })
  }
})

test('viewOf: a foreign token of my folder — a previous load, drawn as mine', () => {
  expect(viewOf({ ok: true, value: tokenOf('old', A) }, 'abc', A)).toEqual({ stale: tokenOf('old', A), foreignRoot: null })
})

test('viewOf: a token of another folder — drawn by me, the second root for the double-load line', () => {
  expect(viewOf({ ok: true, value: tokenOf('xyz', B) }, 'abc', A)).toEqual({ stale: null, foreignRoot: B })
})

test('one instance: the owner after session.start, the pane draws, no double-load line in the pane or in /nod', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1 })
  await startSession(calls, $)
  await startSession(calls, $)
  const ui = await mountPane($, 'desktop')
  expect(await ui.find({ key: 'dec:d-fork' })).toBeDefined()
  expect(await ui.find({ key: 'double-load' })).toBeUndefined()
  const answer = await $.command.run({
    command: 'nod', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 },
  } as never)
  expect(JSON.stringify(answer)).not.toContain('loaded twice')
})

type StateEvent = { key: string; value?: unknown }
type Next = (e: StateEvent) => Promise<{ value?: { value?: unknown; version?: number } }>
const OTHER_TOKEN = 'zzz@' + B

for (const surface of ['desktop', 'terminal'] as const) {
  test(`a drawing writes nothing to $.state: my token, a foreign one of my folder and of another folder on ${surface}`, async ($, on) => {
    let foreign: string | null = null
    let mounting = false
    let root = ''
    const writes: string[] = []
    on('state.get', (async (_: unknown, e: StateEvent, next: Next) => {
      const real = await next(e)

      return foreign !== null && e.key === 'instance' ? { ...real, value: { ...real.value, value: foreign } } : real
    }) as never)
    on('state.set', (async (_: unknown, e: StateEvent, next: (e: StateEvent) => Promise<unknown>) => {
      if (mounting) writes.push(e.key)
      if (e.key === 'instance' && typeof e.value === 'string') root = rootOf(e.value)

      return next(e)
    }) as never)
    const calls = seat(on, { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1 })
    await startSession(calls, $)
    for (const token of [null, 'old@' + root, OTHER_TOKEN]) {
      foreign = token
      mounting = true
      const ui = await mountPane($, surface)
      expect(await ui.find({ key: 'dec:d-fork' })).toBeDefined()
      const warning = await ui.find({ key: 'double-load' })
      if (token === OTHER_TOKEN) expect(warning?.text).toContain('the mod is loaded twice')
      else expect(warning).toBeUndefined()
      await ui.unmount()
      mounting = false
    }
    expect(writes).toEqual([])
  })
}

test('state.get for instance hangs 60 s — the pane draws in 2 s', async ($, on) => {
  let hang = false
  let calls: ReturnType<typeof seat> | null = null
  on('state.get', (async (_: unknown, e: StateEvent, next: Next) => {
    if (hang && e.key === 'instance') await calls!.clock.sleep(60000)

    return next(e)
  }) as never)
  calls = seat(on, { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1 })
  await startSession(calls, $)
  hang = true
  const mounted = mountPane($, 'desktop')
  await calls.clock.advance(2000)
  await calls.clock.settle()
  const ui = await mounted
  expect(await ui.find({ key: 'dec:d-fork' })).toBeDefined()
  hang = false
  await calls.clock.advance(60000)
  await calls.clock.settle()
})
