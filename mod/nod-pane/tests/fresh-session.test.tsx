// A fresh session: the /nod registration is checked against the engine registry ($.command.list()) and writes the
// fact to the transcript; retries come after next(e) in session.start and on the first turn.complete.
// The kit gives no $.command.list() on the test's $ (EventCalls.command has only run and describe), so the registry
// is the world's `command.list` hook in harness.ts, and "in the registry" is checked by the mod's answer and calls.lists.
import { test, expect } from 'claude-code/testing'
import { ROOT, STATE, STATE_FULL } from './fixtures'
import { seat, startSession } from './harness'
import type { Calls } from './harness'

const YES = '/nod registered, in the engine registry: yes (plugin nod)'
const world = (extra: object = {}) => ({ files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1, ...extra })
const loaded = (calls: Calls) => calls.transcript.filter(l => l.startsWith('Nod: mod loaded from '))
const registryLines = (calls: Calls) => calls.transcript.filter(l => l.includes('in the engine registry'))

type Engine = Parameters<Parameters<typeof test>[1]>[0]
const turnDone = ($: Engine, answer = 'answer') => $.turn.complete({
  answer, durationMs: 5, isAborted: false, turnId: 't-1', reason: 'answer',
} as never) as Promise<{ text: string }>
const runNodCommand = ($: Engine) => $.command.run({
  command: 'nod', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 },
} as never) as Promise<{ text?: string }>

test('(a) a fresh session: /nod in the registry from the first session.start, the load line "yes", /nod answers, the pane is open', { options: { diag: true } }, async ($, on) => {
  const calls = seat(on, world())
  await startSession(calls, $)
  expect(calls.registers).toEqual(['nod'])
  expect(calls.lists).toBe(1)
  expect(loaded(calls)).toHaveLength(1)
  expect(loaded(calls)[0]).toMatch(/ · state reset · \/nod registered, in the engine registry: yes \(plugin nod\)$/)
  // "yes" is in the load line already — no retry and no second line.
  expect(registryLines(calls)).toHaveLength(1)
  expect(calls.opens.map(o => o.id)).toEqual(['nod'])
  const ran = await runNodCommand($)
  expect(ran.text).toContain('Nod: pane opened')
  expect(ran.text).toContain(YES)
  // The first answer of a turn: "yes" is there already — neither a registration nor a line; the answer passes as is.
  expect((await turnDone($)).text).toBe('answer')
  await calls.clock.settle()
  expect(calls.registers).toEqual(['nod'])
  expect(registryLines(calls)).toHaveLength(1)
})

test('diagnostics off by default: no load line in the transcript, /nod still answers with the facts', async ($, on) => {
  const calls = seat(on, world())
  await startSession(calls, $)
  expect(loaded(calls)).toHaveLength(0)
  expect(registryLines(calls)).toHaveLength(0)
  const ran = await runNodCommand($)
  expect(ran.text).toContain(YES)
})

test('(b) the first registration refused — "no — <error>" in the load line, the retry after next(e) — "yes"', { options: { diag: true } }, async ($, on) => {
  const calls = seat(on, world({ registerDeny: 'the registry is not ready', registerDenyTimes: 1 }))
  await startSession(calls, $)
  expect(calls.registers).toEqual(['nod', 'nod'])
  expect(loaded(calls)[0]).toMatch(/ · \/nod not registered, in the engine registry: no — .*the registry is not ready.*$/)
  expect(calls.transcript.filter(l => l.includes('the registry is not ready'))).toHaveLength(1)
  const retry = registryLines(calls).filter(l => !l.startsWith('Nod: mod loaded'))
  expect(retry).toEqual([`Nod: registration retry after session start — ${YES}`])
  // Order: the load line (before next) comes before the retry (after next).
  expect(calls.transcript.indexOf(loaded(calls)[0] ?? '')).toBeLessThan(calls.transcript.indexOf(retry[0] ?? ''))
  await turnDone($)
  await calls.clock.settle()
  expect(calls.registers).toHaveLength(2)
})

test('(c) the registration resolved but the list lacks it — "no — the command is not in the list", the retry on the first turn.complete — "yes"', { options: { diag: true } }, async ($, on) => {
  // A list without /nod twice: on the attempt in session.start and on the retry after next(e).
  const calls = seat(on, world({ listHide: 2 }))
  await startSession(calls, $)
  expect(calls.registers).toEqual(['nod', 'nod'])
  expect(loaded(calls)[0]).toMatch(/ · \/nod registered, in the engine registry: no — the command is not in the list$/)
  // The retry after next(e) gave the same fact — no second line.
  expect(registryLines(calls)).toHaveLength(1)
  const answered = await turnDone($, 'done')
  expect(answered.text).toBe('done')
  await calls.clock.settle()
  expect(calls.registers).toEqual(['nod', 'nod', 'nod'])
  expect(registryLines(calls).at(-1)).toBe(`Nod: registration retry after the first answer — ${YES}`)
  // Only the first turn.complete of the session.
  await turnDone($)
  await calls.clock.settle()
  expect(calls.registers).toHaveLength(3)
  expect(registryLines(calls)).toHaveLength(2)
})

test('(c) the command list stays empty after turn.complete — one "no" line, /nod names "no"', { options: { diag: true } }, async ($, on) => {
  const calls = seat(on, world({ listHide: 99 }))
  await startSession(calls, $)
  await turnDone($)
  await calls.clock.settle()
  expect(calls.registers).toHaveLength(3)
  expect(registryLines(calls)).toHaveLength(1)
  const ran = await runNodCommand($)
  expect(ran.text).toContain('/nod registered, in the engine registry: no — the command is not in the list')
})

test('a malformed command.list answer (not an array) — "no — the command list did not answer", the pane opens anyway', { options: { diag: true } }, async ($, on) => {
  const calls = seat(on, world({ listNull: true }))
  await startSession(calls, $)
  expect(loaded(calls)[0]).toMatch(/ · \/nod registered, in the engine registry: no — the command list did not answer/)
  expect(calls.opens.map(o => o.id)).toEqual(['nod'])
})

test('command.register hangs — the start and the pane wait no longer than 2 s, the fact "no — registration did not answer in 2 s"', { options: { diag: true } }, async ($, on) => {
  const calls = seat(on, world({ registerHangTimes: 2 }))
  const started = $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true } as never)
  await calls.clock.advance(2000)
  await started
  await calls.clock.settle()
  // The retry (b) hangs, and the pane is open already: it does not hold the opening.
  expect(calls.registers).toEqual(['nod', 'nod'])
  expect(calls.opens.map(o => o.id)).toEqual(['nod'])
  expect(loaded(calls)[0]).toMatch(/ · \/nod not registered, in the engine registry: no — registration did not answer in 2 s$/)
  await calls.clock.advance(2000)
  await calls.clock.settle()
  // The retry gave the same fact — no second line; the first answer registers successfully.
  expect(registryLines(calls)).toHaveLength(1)
  await turnDone($)
  await calls.clock.settle()
  expect(registryLines(calls).at(-1)).toBe(`Nod: registration retry after the first answer — ${YES}`)
})

test('turn.complete of a subagent is not the first answer of the session', async ($, on) => {
  const calls = seat(on, world({ listHide: 2 }))
  await startSession(calls, $)
  await $.turn.complete({ answer: 'report', durationMs: 1, isAborted: false, turnId: 't-a', reason: 'answer', agentId: 'a-1' } as never)
  await calls.clock.settle()
  expect(calls.registers).toHaveLength(2)
  await turnDone($)
  await calls.clock.settle()
  expect(calls.registers).toHaveLength(3)
})
