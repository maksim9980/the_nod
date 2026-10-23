import { test, expect } from 'claude-code/testing'
import { markPress, renderLines, slowRenderLine, timed } from '../hooks/log'

const fake = () => {
  const logs: string[] = []
  const $ = { ui: { log: async (text: string) => { logs.push(text) } } }

  return { $: $ as never, logs }
}

const drain = () => new Promise(resolve => setTimeout(resolve, 10))

test('timed returns the result and writes "label — ms, tail"', async () => {
  const { $, logs } = fake()
  expect(await timed($, 'nod decision answer', async () => 7, n => 'code ' + n)).toBe(7)
  await drain()
  expect(logs).toHaveLength(1)
  expect(logs[0]).toMatch(/^nod: nod decision answer — \d+ ms, code 7$/)
})

test('timed logs an error and rethrows it', async () => {
  const { $, logs } = fake()
  await expect(timed($, 'nod status', async () => { throw new Error('no python') })).rejects.toThrow('no python')
  await drain()
  expect(logs).toHaveLength(1)
  expect(logs[0]).toMatch(/^nod: nod status — \d+ ms, error: no python$/)
})

test('timed with a failing log does not break the work', async () => {
  const $ = { ui: { log: async () => { throw new Error('no log') } } }
  expect(await timed($ as never, 'nod status', async () => 'ok')).toBe('ok')
})

test('the render line only for a drawing longer than 200 ms', () => {
  expect(slowRenderLine(200)).toBeNull()
  expect(slowRenderLine(201)).toBe('render — 201 ms')
})

test('after a press: the first drawing always in the log, "saving…" once, when pending arrived', () => {
  markPress()
  const started = Date.now()
  const first = renderLines(started, null)
  expect(first).toHaveLength(1)
  expect(first[0]).toMatch(/^render after click — \d+ ms$/)
  const shown = renderLines(Date.now(), 'd-fork')
  expect(shown).toHaveLength(1)
  expect(shown[0]).toMatch(/^“saving…” shown \+\d+ ms$/)
  expect(renderLines(Date.now(), 'd-fork')).toEqual([])
})
