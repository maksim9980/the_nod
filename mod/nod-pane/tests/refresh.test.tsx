import { test, expect } from 'claude-code/testing'
import { DIR, NOD, STATE, STATE_FULL } from './fixtures'
import { stateFile } from '../hooks/find'
import { parseSnapshot } from '../hooks/snapshot'
import type { Waiting } from '../hooks/snapshot'
import { mountPane, seat, startSession } from './harness'

const SHOWN = /^D:\\x\\proj\\\.nod\\state\.json: /

const textOf = async ($: Parameters<typeof mountPane>[0], key: string) => {
  const ui = await mountPane($, 'desktop')
  const text = (await ui.find({ key }))?.text
  await ui.unmount()

  return text
}

const statusText = ($: Parameters<typeof mountPane>[0]) => textOf($, 'zone:waiting:title')
const errorText = ($: Parameters<typeof mountPane>[0]) => textOf($, 'load-error')

test('at the start calls nod status, reads the snapshot and shows the number waiting', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1 })
  await startSession(calls, $)
  expect(calls.runs).toContainEqual([...NOD, '--root', DIR, 'status'])
  expect(await statusText($)).toBe('Waiting for you · 3')
})

test('the 15 s timer rereads only on a new mtime', async ($, on) => {
  const world = { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1 }
  const calls = seat(on, world)
  await startSession(calls, $)
  const n = calls.reads.length
  await calls.clock.advance(15000)
  await calls.clock.settle()
  expect(calls.reads).toHaveLength(n)
  world.mtime = 2
  await calls.clock.advance(15000)
  await calls.clock.settle()
  expect(calls.reads).toHaveLength(n + 1)
})

test('ui.render and tool.call after the start do not arm a second timer', async ($, on) => {
  const world = { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1 }
  on('tool.call', () => ({ result: {} }))
  const calls = seat(on, world)
  await startSession(calls, $)
  const ui = await mountPane($, 'desktop')
  await $.tool.call({ tool: 'mcp__t__x' })
  await calls.clock.settle()
  await ui.unmount()
  const n = calls.reads.length
  const s = calls.stats.length
  world.mtime = 2
  await calls.clock.advance(15000)
  await calls.clock.settle()
  expect(calls.reads).toHaveLength(n + 1)
  // One timer — one stat per tick; a second timer would give two.
  expect(calls.stats).toHaveLength(s + 1)
  await calls.clock.advance(15000)
  await calls.clock.settle()
  expect(calls.stats).toHaveLength(s + 2)
})

test('after tool.call rereads on a changed mtime', async ($, on) => {
  const world = { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1 }
  on('tool.call', () => ({ result: {} }))
  const calls = seat(on, world)
  await startSession(calls, $)
  const n = calls.reads.length
  world.mtime = 3
  await $.tool.call({ tool: 'mcp__t__x' })
  await calls.clock.settle()
  expect(calls.reads).toHaveLength(n + 1)
})

test('broken JSON — an error line, the old snapshot stays', async ($, on) => {
  const world: { files: Record<string, string>; mtime: number } = { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1 }
  const calls = seat(on, world)
  await startSession(calls, $)
  world.files[STATE] = '{'
  world.mtime = 2
  await calls.clock.advance(15000)
  await calls.clock.settle()
  expect(await errorText($)).toMatch(/^D:\\x\\proj\\\.nod\\state\.json: not JSON/)
  expect(await statusText($)).toBe('Waiting for you · 3')
})

test('schema 2 — "schema 2, the mod knows 1"', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: JSON.stringify({ ...STATE_FULL, schema: 2 }) }, mtime: 1 })
  await startSession(calls, $)
  const text = await errorText($)
  expect(text).toMatch(SHOWN)
  expect(text).toBe(STATE + ': schema 2, the mod knows 1')
})

test('waiting: {} — "field waiting is not an array", the old snapshot stays', async ($, on) => {
  const world: { files: Record<string, string>; mtime: number } = { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1 }
  const calls = seat(on, world)
  await startSession(calls, $)
  world.files[STATE] = JSON.stringify({ ...STATE_FULL, waiting: {} })
  world.mtime = 2
  await calls.clock.advance(15000)
  await calls.clock.settle()
  expect(await errorText($)).toBe(STATE + ': field waiting is not an array')
  expect(await statusText($)).toBe('Waiting for you · 3')
})

test('the shape of the snapshot arrays and numbers is checked before the atom write', () => {
  const bad = (patch: object) => {
    const r = parseSnapshot(JSON.stringify({ ...STATE_FULL, ...patch }))

    return 'error' in r ? r.error : null
  }
  expect(bad({ running: 'x' })).toBe('field running is not an array')
  expect(bad({ backlog: { total: 1, top: {} } })).toBe('field backlog.top is not an array')
  expect(bad({ backlog: { total: '1', top: [] } })).toBe('field backlog.total is not a number')
  expect(bad({ since: { ...STATE_FULL.since, cards_done: null } })).toBe('field since.cards_done is not an array')
  const ver = STATE_FULL.waiting[1] as Waiting
  expect(bad({ waiting: [STATE_FULL.waiting[0], { ...ver, acceptance: { ...ver.acceptance, frames: {} } }] }))
    .toBe('field waiting[1].acceptance.frames is not an array')
  expect(bad({ waiting: [{ ...ver, acceptance: { ...ver.acceptance, steps: 'a' } }] }))
    .toBe('field waiting[0].acceptance.steps is not an array')
  expect(bad({ waiting: [{ ...ver, acceptance: null }] })).toBeNull()
  expect(bad({})).toBeNull()
})

test('a foreign core rebuild moved since.from — one status --peek --since from the previous point', async ($, on) => {
  const world: { files: Record<string, string>; mtime: number } = { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1 }
  const calls = seat(on, world)
  await startSession(calls, $)
  const foreign = JSON.stringify({ ...STATE_FULL, since: { ...STATE_FULL.since, from: '2026-10-20T10:00:00' } })
  world.files[STATE] = foreign
  world.mtime = 2
  await calls.clock.advance(15000)
  await calls.clock.settle()
  const reanchor = [...NOD, '--root', DIR, 'status', '--peek', '--no-sync', '--since', '2026-10-17T00:00:00']
  const count = () => calls.runs.filter(r => JSON.stringify(r) === JSON.stringify(reanchor)).length
  expect(count()).toBe(1)
  // The core did not rebuild the file (the world is silent): the same foreign point with a new mtime gives no second run.
  world.mtime = 3
  await calls.clock.advance(15000)
  await calls.clock.settle()
  expect(count()).toBe(1)
})

test('our since.from came back, then a foreign one again — another re-anchor', async ($, on) => {
  const world: { files: Record<string, string>; mtime: number } = { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1 }
  const own = JSON.stringify(STATE_FULL)
  const foreign = JSON.stringify({ ...STATE_FULL, since: { ...STATE_FULL.since, from: '2026-10-20T10:00:00' } })
  const calls = seat(on, {
    ...world,
    get files() { return world.files },
    get mtime() { return world.mtime },
    run: argv => {
      if (argv.includes('--since')) { world.files[STATE] = own; world.mtime += 1 }

      return {}
    },
  })
  await startSession(calls, $)
  const tick = async () => {
    world.files[STATE] = foreign
    world.mtime += 1
    await calls.clock.advance(15000)
    await calls.clock.settle()
  }
  await tick()
  await tick()
  expect(calls.runs.filter(r => r.includes('--since'))).toHaveLength(2)
  expect(await statusText($)).toBe('Waiting for you · 3')
})

test('the file is gone — "no file — run nod status"', async ($, on) => {
  const world: { files: Record<string, string>; mtime: number } = { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1 }
  const calls = seat(on, world)
  await startSession(calls, $)
  delete world.files[STATE]
  await calls.clock.advance(15000)
  await calls.clock.settle()
  expect(await errorText($)).toBe(STATE + ': no file — run nod status')
  expect(await statusText($)).toBe('Waiting for you · 3')
})

test('a POSIX path: state.json is looked up with "/", the pane shows the number waiting', async ($, on) => {
  const file = '/home/x/proj/.nod/state.json'
  const calls = seat(on, { files: { [file]: JSON.stringify(STATE_FULL) }, mtime: 1 })
  await startSession(calls, $, '/home/x/proj/src')
  expect(calls.reads.map(p => p.replace(/^[A-Za-z]:/, '').replace(/\\/g, '/'))).toContain(file)
  expect(await statusText($)).toBe('Waiting for you · 3')
})

test('nod status failed — the reason in loadError, a readable file is shown anyway', async ($, on) => {
  const calls = seat(on, {
    files: { [STATE]: JSON.stringify(STATE_FULL) },
    mtime: 1,
    run: argv => argv.includes('status')
      ? { exitCode: 3, stderr: 'error: state not fresh since 2026-10-20T09:00:00: run git pull first\n' }
      : {},
  })
  await startSession(calls, $)
  expect(await errorText($)).toBe('nod status: state not fresh since 2026-10-20T09:00:00: run git pull first')
  expect(await statusText($)).toBe('Waiting for you · 3')
})

test('since without from — "no field since.from"', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: JSON.stringify({ ...STATE_FULL, since: {} }) }, mtime: 1 })
  await startSession(calls, $)
  expect(await errorText($)).toBe(STATE + ': no field since.from')
})

test('fs.read refused after stat — an error with the path', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '' }, mtime: 1, readDeny: 'EIO' })
  await startSession(calls, $)
  expect(await errorText($)).toMatch(/^D:\\x\\proj\\\.nod\\state\.json: .*EIO/)
})

test('stateFile takes the separator from the path', () => {
  expect(stateFile('/home/x/proj/.nod')).toBe('/home/x/proj/.nod/state.json')
  expect(stateFile(DIR)).toBe(STATE)
})
