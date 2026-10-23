// Writing an answer does not depend on the pane state: a refused or hanging `$.state.set` on the click path shows in
// the status line, and `nod decision answer` goes out anyway.
import { test, expect } from 'claude-code/testing'
import { STATE, STATE_FULL } from './fixtures'
import { mountPane, runNod, seat, startSession } from './harness'
import type { World } from './harness'

const NOW = Date.parse('2026-10-20T10:12:00')
const world = (extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1, now: NOW, ...extra })
const ANSWER = runNod(['decision', 'answer', '--', 'd-fork', 'ISO'])
const decisionRuns = (runs: (readonly string[])[]) => runs.filter(r => r.includes('decision'))

type SetEvent = { key: string }
type Next = (e: SetEvent) => Promise<unknown>

/** Status lines in order: each next one comes later than the previous one. */
const inOrder = (statuses: string[], patterns: RegExp[]): boolean => {
  let from = 0
  for (const p of patterns) {
    const at = statuses.findIndex((s, i) => i >= from && p.test(String(s)))
    if (at < 0) return false
    from = at + 1
  }

  return true
}

// pending, progress, writeError and lastAction are module variables, $.state does not write them.
const CLICK_KEYS = ['pending', 'progress', 'writeError', 'lastAction']

for (const surface of ['desktop', 'terminal'] as const) {
  test(`(h) $.state refuses everything: "saving…" shows, the write goes, the buttons come back on ${surface}`, async ($, on) => {
    let deny = false
    const keys: string[] = []
    // The test's hook sits above the bottom of $.state: other keys pass down through next.
    on('state.set', (async (_: unknown, e: SetEvent, next: Next) => {
      keys.push(e.key)

      return deny ? { deny: 'forbidden' } : next(e)
    }) as never)
    const calls: ReturnType<typeof seat> = seat(on, world({
      run: async argv => {
        if (argv.includes('decision')) await calls.clock.sleep(1000)

        return {}
      },
    }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    deny = true
    await ui.press({ key: 'opt:d-fork:0' })
    expect((await ui.find({ key: 'busy:d-fork' }))?.text).toBe('saving…')
    await calls.clock.advance(1000)
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toEqual([ANSWER])
    expect(await ui.find({ key: 'busy:d-fork' })).toBeUndefined()
    expect(await ui.find({ key: 'opt:d-fork:0' })).toBeDefined()
    expect(keys.filter(k => CLICK_KEYS.includes(k))).toEqual([])
    await ui.press({ key: 'opt:d-fork:0' })
    await calls.clock.advance(1000)
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toEqual([ANSWER, ANSWER])
  })

  test(`(h2) state.set refused for snapshot: the write goes, the status names the refusal on ${surface}`, async ($, on) => {
    let deny = false
    on('state.set', (async (_: unknown, e: SetEvent, next: Next) =>
      (deny && e.key === 'snapshot' ? { deny: 'forbidden' } : next(e))) as never)
    const calls = seat(on, world())
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    deny = true
    await ui.press({ key: 'opt:d-fork:0' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toEqual([ANSWER])
    expect(inOrder(calls.statuses, [
      /^Nod: pressed “ISO”…$/,
      /^Nod: saved d-fork · \d+ ms$/,
      /^Nod: pane state does not respond \(snapshot: .*forbidden\) — going on$/,
    ])).toBe(true)
    expect((await ui.find({ key: 'last-action' }))?.text)
      .toMatch(/^last action: answer d-fork · \d+ ms · ok · pane state does not respond \(snapshot: /)
  })

  test(`(i) state.set for loadError and snapshot hangs: the write does not wait, the status "timeout 2 s" on ${surface}`, async ($, on) => {
    let hang = false
    let calls: ReturnType<typeof seat> | null = null
    on('state.set', (async (_: unknown, e: SetEvent, next: Next) => {
      if (hang && (e.key === 'snapshot' || e.key === 'loadError')) await calls!.clock.sleep(10000)

      return next(e)
    }) as never)
    calls = seat(on, world())
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    hang = true
    await ui.press({ key: 'opt:d-fork:0' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toEqual([ANSWER])
    await calls.clock.advance(2000)
    await calls.clock.settle()
    expect(calls.statuses).toContain('Nod: pane state does not respond (snapshot: timeout 2 s) — going on')
    expect(await ui.find({ key: 'opt:d-fork:0' })).toBeDefined()
    hang = false
    await calls.clock.advance(12000)
    await calls.clock.settle()
  })
}

// Reads on the click path are bounded by 2 s; nodPrefix and stateDir come from the start copies when silent.
// The first read of a key after the flag hangs — it is the click path's read. The kit does not wind repeatedly
// put-to-sleep reads of every redraw: advance does not return then (checked by a probe).
type GetNext = (e: SetEvent) => Promise<unknown>

test('state.get for nodPrefix and stateDir hangs: after 2 s the write goes by the start copies, the status names the swap', async ($, on) => {
  let hang = false
  const hung = new Set<string>()
  let calls: ReturnType<typeof seat> | null = null
  on('state.get', (async (_: unknown, e: SetEvent, next: GetNext) => {
    if (hang && (e.key === 'nodPrefix' || e.key === 'stateDir') && !hung.has(e.key)) {
      hung.add(e.key)
      await calls!.clock.sleep(60000)
    }

    return next(e)
  }) as never)
  calls = seat(on, world())
  await startSession(calls, $)
  const ui = await mountPane($, 'desktop')
  hang = true
  // The press act waits for all the handler's work, the hanging read included: wait for it at the end.
  const pressed = ui.press({ key: 'opt:d-fork:0' })
  await calls.clock.settle()
  expect(decisionRuns(calls.runs)).toHaveLength(0)
  await calls.clock.advance(2000)
  await calls.clock.settle()
  expect(decisionRuns(calls.runs)).toEqual([ANSWER])
  expect(calls.statuses.some(s => /^Nod: pane state does not respond \((nodPrefix|stateDir): timeout 2 s; taking the value from session start\) — going on$/.test(String(s))))
    .toBe(true)
  hang = false
  await calls.clock.advance(60000)
  await calls.clock.settle()
  await pressed
})

test('state.get for snapshot hangs: "all" — a skip "pane state does not respond (snapshot…)" in 2 s, the lock is free', async ($, on) => {
  let hang = false
  const hung = new Set<string>()
  let calls: ReturnType<typeof seat> | null = null
  on('state.get', (async (_: unknown, e: SetEvent, next: GetNext) => {
    if (hang && e.key === 'snapshot' && !hung.has(e.key)) {
      hung.add(e.key)
      await calls!.clock.sleep(60000)
    }

    return next(e)
  }) as never)
  calls = seat(on, world())
  await startSession(calls, $)
  const ui = await mountPane($, 'desktop')
  hang = true
  const all = ui.press({ key: 'answer-all' })
  await calls.clock.settle()
  await calls.clock.advance(2000)
  await calls.clock.settle()
  expect(calls.statuses).toContain('Nod: ignored — pane state does not respond (snapshot: timeout 2 s)')
  expect(decisionRuns(calls.runs)).toEqual([])
  // The lock is not held: the next click writes.
  const one = ui.press({ key: 'opt:d-fork:0' })
  await calls.clock.settle()
  await calls.clock.advance(2000)
  await calls.clock.settle()
  expect(decisionRuns(calls.runs)).toEqual([ANSWER])
  hang = false
  await calls.clock.advance(60000)
  await calls.clock.settle()
  await Promise.all([all, one])
})

test('/nod — the diagnostics channel: the last status line and the last action', async ($, on) => {
  const calls = seat(on, world())
  await startSession(calls, $)
  const ui = await mountPane($, 'desktop')
  await ui.press({ key: 'opt:d-fork:0' })
  await calls.clock.settle()
  const ran = await $.command.run({
    command: 'nod', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 },
  } as never) as { text?: string }
  expect(ran.text).toMatch(/\nlast press: Nod: saved d-fork · \d+ ms(\n|$)/)
  expect(ran.text).toMatch(/\nlast action: answer d-fork · \d+ ms · ok/)
})
