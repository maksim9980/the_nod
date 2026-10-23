// Where /nod is registered: only in session.start and on the first turn.complete. Drawing and tool.call do not
// register the command: a $ call with its own hook chain while drawing risks a re-entry.
import { test, expect } from 'claude-code/testing'
import { STATE, STATE_FULL } from './fixtures'
import { mountPane, seat, startSession } from './harness'

test('(d) drawing and tool.call do not call command.register; /nod works', async ($, on) => {
  on('tool.call', () => ({ result: {} }))
  const calls = seat(on, { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1 })
  await startSession(calls, $)
  expect(calls.registers).toEqual(['nod'])
  const before = calls.registers.length
  const ui = await mountPane($, 'desktop')
  await calls.clock.settle()
  await ui.redraw()
  await calls.clock.settle()
  expect(calls.registers.length - before).toBe(0)
  await $.tool.call({ tool: 'mcp__t__x' } as never)
  await calls.clock.settle()
  expect(calls.registers).toEqual(['nod'])
  const ran = await $.command.run({
    command: 'nod', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 },
  } as never) as { text?: string }
  expect(ran.text).toContain('Nod: pane opened')
})

test('(d) command.register always refused — the reason in the load line, no second line with the same reason', { options: { diag: true } }, async ($, on) => {
  const calls = seat(on, { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1, registerDeny: 'forbidden' })
  await startSession(calls, $)
  expect(calls.registers).toEqual(['nod', 'nod'])
  expect(calls.transcript.some(l => / · \/nod not registered, in the engine registry: no — .*forbidden.*$/.test(l))).toBe(true)
  expect(calls.transcript.filter(l => l.includes('forbidden'))).toHaveLength(1)
})
