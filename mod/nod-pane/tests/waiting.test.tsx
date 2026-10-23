import { local } from '../hooks/local'
import { test, expect } from 'claude-code/testing'
import { DIR, STATE, STATE_FULL, STATE_STALE } from './fixtures'
import { mountPane, runNod, seat, startSession, writeButtons } from './harness'
import type { Calls, World } from './harness'
import { answerArgs, makeActions } from '../hooks/actions'
import { renderLines } from '../hooks/log'
import type { Snapshot, Waiting } from '../hooks/snapshot'
import type { Cell, PaneState } from '../hooks/state'

const STATUS_AFTER = ['status', '--peek', '--no-sync', '--since', '2026-10-17T00:00:00']
const NOW = Date.parse('2026-10-20T10:12:00')

const world = (state: unknown, extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(state) }, mtime: 1, now: NOW, ...extra })

const decisionRuns = (runs: (readonly string[])[]) => runs.filter(r => r.includes('decision'))
const FORK = STATE_FULL.waiting[0] as Waiting

for (const surface of ['desktop', 'terminal'] as const) {
  test(`a fork: options as buttons, the proposed one primary, a press writes the answer on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'opt:d-fork:0' }))?.props)
      .toMatchObject({ label: 'ISO · proposed', variant: 'primary', hotkey: '1' })
    expect((await ui.find({ key: 'opt:d-fork:1' }))?.props?.variant).not.toBe('primary')
    expect((await ui.find({ key: 'dec:d-fork' }))?.text).toContain('Every spreadsheet reads ISO')
    expect((await ui.find({ key: 'dec:d-fork' }))?.text).toContain('Write dates to the CSV in ISO')
    await ui.press({ key: 'opt:d-fork:1' })
    await calls.clock.settle()
    expect(calls.runs.at(-2)).toEqual(runNod(['decision', 'answer', '--', 'd-fork', 'Local format']))
    expect(calls.runs.at(-1)).toEqual(runNod(STATUS_AFTER))
  })

  test(`during a write there are no write buttons anywhere, a second write does not start on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, {
      run: async argv => {
        if (argv.includes('decision')) await calls.clock.sleep(1000)

        return {}
      },
    }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-fork:1' })
    await calls.clock.settle()
    await expect(ui.press({ key: 'opt:d-fork:0' })).rejects.toThrow(/no Button/)
    expect(await writeButtons(ui)).toHaveLength(0)
    expect((await ui.find({ key: 'busy:d-fork' }))?.text).toBe('saving…')
    expect(decisionRuns(calls.runs)).toHaveLength(1)
    await calls.clock.advance(1000)
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toHaveLength(1)
    expect(await ui.find({ key: 'busy:d-fork' })).toBeUndefined()
  })

  test(`"saving…" shows right after the press, without the clock moving on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, {
      run: async argv => {
        if (argv.includes('decision')) await calls.clock.sleep(1000)

        return {}
      },
    }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-fork:1' })
    expect((await ui.find({ key: 'busy:d-fork' }))?.text).toBe('saving…')
    expect(await writeButtons(ui)).toHaveLength(0)
    // The click state is in the module: a redraw is asked by invalidate, not by an atom write.
    expect(calls.invalidates.length).toBeGreaterThan(0)
    expect(calls.invalidates.every(x => x === 'ui.render')).toBe(true)
    await calls.clock.settle()
    await calls.clock.advance(1000)
    await calls.clock.settle()
    expect(calls.logs.filter(l => /^nod: “saving…” shown \+\d+ ms$/.test(l))).toHaveLength(1)
    expect(calls.logs.filter(l => /^nod: render after click — \d+ ms$/.test(l))).toHaveLength(1)
  })

  test(`a press writes the nod duration and the click summary line to the debug log on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-fork:1' })
    await calls.clock.settle()
    expect(calls.logs.some(l => /^nod: nod decision answer — \d+ ms, code 0$/.test(l))).toBe(true)
    expect(calls.logs.filter(l => /^nod: click d-fork: pending \+\d+ ms, nod answer \d+ ms, reread \+\d+ ms, buttons back \+\d+ ms$/.test(l)))
      .toHaveLength(1)
    expect(calls.logs.filter(l => /^nod: re-anchor d-fork — \d+ ms$/.test(l))).toHaveLength(1)
    expect(calls.logs.some(l => /^nod: nod status --peek — \d+ ms, code 0$/.test(l))).toBe(true)
  })

  test(`code 3 — "not saved" without "error: ", Retry sends the same argv, the decision stays on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, {
      run: argv => (argv.includes('decision')
        ? { exitCode: 3, stderr: 'error: state not fresh since 2026-10-20T09:00:00: run git pull first\n' }
        : {}),
    }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-fork:1' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'err:d-fork' }))?.text)
      .toBe('not saved: state not fresh since 2026-10-20T09:00:00: run git pull first')
    expect(await ui.find({ key: 'dec:d-fork' })).toBeDefined()
    await ui.press({ key: 'retry:d-fork' })
    await calls.clock.settle()
    const runs = decisionRuns(calls.runs)
    expect(runs).toHaveLength(2)
    expect(runs[1]).toEqual(runs[0])
    expect(runs[1]).toEqual(runNod(['decision', 'answer', '--', 'd-fork', 'Local format']))
  })

  test(`process.run refused — "could not start nod" on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, {
      run: argv => {
        return argv.includes('decision') ? { deny: 'forbidden' } : {}
      },
    }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-fork:1' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'err:d-fork' }))?.text).toMatch(/^not saved: could not start nod/)
    expect(await ui.find({ key: 'retry:d-fork' })).toBeDefined()
    expect(await ui.find({ key: 'busy:d-fork' })).toBeUndefined()
  })

  test(`after a successful write the snapshot the core rebuilt is reread, then a re-anchor on ${surface}`, async ($, on) => {
    const w = world(STATE_FULL)
    // The core rebuilds state.json itself inside `decision answer`; the re-anchor rebuilds it again from the visit point.
    w.run = argv => {
      if (argv.includes('decision')) {
        w.files[STATE] = JSON.stringify({ ...STATE_FULL, waiting: STATE_FULL.waiting.filter(x => x.id !== 'd-fork') })
        w.mtime = 2
      }

      return {}
    }
    const calls = seat(on, w)
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'dec:d-fork' })).toBeDefined()
    await ui.press({ key: 'opt:d-fork:0' })
    await calls.clock.settle()
    expect(calls.runs.at(-1)).toEqual(runNod(STATUS_AFTER))
    expect(await ui.find({ key: 'dec:d-fork' })).toBeUndefined()
    expect(await ui.find({ key: 'err:d-fork' })).toBeUndefined()
    expect(await ui.find({ key: 'dec:d-ver2' })).toBeDefined()
  })

  test(`the card goes and the buttons come back before the re-anchor ends on ${surface}`, async ($, on) => {
    const w = world(STATE_FULL)
    const calls = seat(on, w)
    w.run = async argv => {
      if (argv.includes('decision')) {
        w.files[STATE] = JSON.stringify({ ...STATE_FULL, waiting: STATE_FULL.waiting.filter(x => x.id !== 'd-fork') })
        w.mtime = 2
      }
      if (argv.includes('--peek')) await calls.clock.sleep(1000)

      return {}
    }
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-fork:0' })
    await calls.clock.settle()
    expect(await ui.find({ key: 'dec:d-fork' })).toBeUndefined()
    expect(await ui.find({ key: 'busy:d-fork' })).toBeUndefined()
    expect(await ui.find({ key: 'accept:d-ver2' })).toBeDefined()
    expect(await ui.find({ key: 'answer-all' })).toBeDefined()
    await calls.clock.advance(1000)
    await calls.clock.settle()
    expect(calls.runs).toContainEqual(runNod(STATUS_AFTER))
  })

  test(`the next write waits for the background re-anchor, "saving…" shows at once on ${surface}`, async ($, on) => {
    const w = world(STATE_FULL)
    const calls = seat(on, w)
    w.run = async argv => {
      if (argv.includes('decision') && argv.includes('d-fork')) {
        w.files[STATE] = JSON.stringify({ ...STATE_FULL, waiting: STATE_FULL.waiting.filter(x => x.id !== 'd-fork') })
        w.mtime = 2
      }
      if (argv.includes('--peek')) await calls.clock.sleep(1000)

      return {}
    }
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-fork:0' })
    await calls.clock.settle()
    await ui.press({ key: 'accept:d-ver2' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'busy:d-ver2' }))?.text).toBe('saving…')
    expect(calls.runs.filter(r => r.includes('d-ver2'))).toHaveLength(0)
    await calls.clock.advance(1000)
    await calls.clock.settle()
    expect(calls.runs.filter(r => r.includes('d-ver2'))).toHaveLength(1)
    await calls.clock.advance(1000)
    await calls.clock.settle()
    expect(await ui.find({ key: 'busy:d-ver2' })).toBeUndefined()
  })

  test(`a new session during a write takes "saving…" off (session.start clears the click state) on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, {
      run: async argv => {
        if (argv.includes('decision')) await calls.clock.sleep(1000)

        return {}
      },
    }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-fork:1' })
    await calls.clock.settle()
    expect(await ui.find({ key: 'busy:d-fork' })).toBeDefined()
    await startSession(calls, $)
    expect(await ui.find({ key: 'busy:d-fork' })).toBeUndefined()
    // The snapshot is reset too: the start nod status waits for the slot the running write holds.
    await calls.clock.advance(1000)
    await calls.clock.settle()
    expect(await ui.find({ key: 'opt:d-fork:0' })).toBeDefined()
  })

  test(`with STATE_STALE there are no write buttons, the cards are there on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_STALE))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'dec:d-fork' })).toBeDefined()
    expect(await ui.find({ key: 'dec:d-ver1' })).toBeDefined()
    expect(await writeButtons(ui)).toHaveLength(0)
  })

  test(`a 300-character question, 15 options and guillemets in an option pass, the label is clipped to 60, argv is whole on ${surface}`, async ($, on) => {
    const long = '«' + 'x'.repeat(80) + '»'
    const options = Array.from({ length: 15 }, (_, i) => (i === 3 ? long : `Option ${i}`))
    const state = {
      ...STATE_FULL,
      waiting: [{ ...FORK, question: 'q'.repeat(300), options, proposed: 'Option 0' }],
    }
    const calls = seat(on, world(state))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'dec:d-fork' }))?.text).toContain('q'.repeat(300))
    const buttons = (await ui.findAll({ type: 'Button' })).filter(b => String(b.key).startsWith('opt:'))
    expect(buttons).toHaveLength(15)
    const label = String((await ui.find({ key: 'opt:d-fork:3' }))?.props?.label)
    expect(label).toHaveLength(60)
    expect(label.endsWith('…')).toBe(true)
    expect(label.startsWith('«xxx')).toBe(true)
    await ui.press({ key: 'opt:d-fork:3' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)[0]).toEqual(runNod(['decision', 'answer', '--', 'd-fork', long]))
  })

  test(`proposed outside options — the proposed button first, the answer with --free on ${surface}`, async ($, on) => {
    const state = {
      ...STATE_FULL,
      waiting: [{ ...FORK, proposed: 'My own option', options: ['A', 'B'] }],
    }
    const calls = seat(on, world(state))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'opt:d-fork:0' }))?.props)
      .toMatchObject({ label: 'My own option · proposed', variant: 'primary', hotkey: '1' })
    expect((await ui.find({ key: 'opt:d-fork:1' }))?.props?.label).toBe('A')
    await ui.press({ key: 'opt:d-fork:0' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)[0]).toEqual(runNod(['decision', 'answer', '--free', '--', 'd-fork', 'My own option']))
  })
}

function cell<T>(value: T): Cell<T> & { value: T } {
  const c = { value, read: async () => c.value, write: async (v: T) => { c.value = v } }

  return c
}

test('two presses in one tick give one nod run: the lock stands before await', async () => {
  const runs: (readonly string[])[] = []
  const st = {
    stateDir: cell<string | null>(DIR), nodPrefix: cell<readonly string[] | null | 'unknown'>(['nod']),
    snapshot: cell(null), loadError: cell<string | null>(null), lastMtime: cell(0), sinceFrom: cell<string | null>(null),
    pending: cell<string | null>(null), writeError: cell(null), draft: cell(''), expanded: cell<string[]>([]),
    freeFor: cell<string | null>(null),
  }
  const $ = {
    plugin: { root: 'D:/mod' },
    process: {
      run: async (argv: readonly string[]) => {
        runs.push(argv)

        return { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
      },
    },
    fs: { stat: async () => { throw new Error('no file') }, read: async () => '' },
  }
  const a = makeActions($ as never, st as unknown as PaneState)
  a.answer('d-fork', 'A')
  a.answer('d-fork', 'B')
  await new Promise(resolve => setTimeout(resolve, 20))
  expect(runs.filter(r => r.includes('decision'))).toHaveLength(1)
  expect(local.pending).toBeNull()
})

test('a click: pending is set in the module synchronously, before any state call and process.run', async () => {
  const journal: string[] = []
  function logged<T>(name: string, value: T): Cell<T> & { value: T } {
    const c = {
      value,
      read: async () => { journal.push(name + '.read'); return c.value },
      write: async (v: T) => { journal.push(`${name}.write(${String(v)})`); c.value = v },
    }

    return c
  }
  const st = {
    stateDir: logged<string | null>('stateDir', DIR), nodPrefix: logged<readonly string[] | null | 'unknown'>('nodPrefix', ['nod']),
    snapshot: logged('snapshot', null), loadError: logged<string | null>('loadError', null), lastMtime: logged('lastMtime', 0),
    sinceFrom: logged<string | null>('sinceFrom', null), pending: logged<string | null>('pending', null),
    progress: logged('progress', null), writeError: logged('writeError', null), draft: logged('draft', ''),
    expanded: logged<string[]>('expanded', []), freeFor: logged<string | null>('freeFor', null),
  }
  const $ = {
    plugin: { root: 'D:/mod' },
    process: {
      run: async (argv: readonly string[]) => {
        journal.push('process.run ' + argv.join(' '))

        return { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
      },
    },
    fs: { stat: async () => { throw new Error('no file') }, read: async () => '' },
    ui: { log: async () => undefined, invalidate: () => undefined },
    clock: { now: async () => 0 },
  }
  makeActions($ as never, st as unknown as PaneState).answer('d-fork', 'A')
  expect(local.pending).toBe('d-fork')
  expect(journal).toEqual([])
  await new Promise(resolve => setTimeout(resolve, 20))
  expect(journal.some(x => x.startsWith('pending.'))).toBe(false)
  expect(journal.findIndex(x => x.startsWith('process.run'))).toBeGreaterThan(0)
})

/** A world where peek sleeps `ms` by the test clock; counts how many peeks run at once. */
const sleepingPeek = (state: unknown, extra: Partial<World>, sleep: () => Promise<void>) => {
  const seen = { inFlight: 0, max: 0 }
  const w = world(state, {
    ...extra,
    run: async argv => {
      if (argv.includes('--peek')) {
        seen.inFlight += 1
        seen.max = Math.max(seen.max, seen.inFlight)
        await sleep()
        seen.inFlight -= 1

        return {}
      }

      return extra.run === undefined ? {} : extra.run(argv)
    },
  })

  return { w, seen }
}

const decisionAfterPeek = (runs: (readonly string[])[]) => {
  const peek = runs.findIndex(r => r.includes('--peek'))
  const decision = runs.findIndex(r => r.includes('decision'))

  return peek >= 0 && decision > peek
}

test('a timer peek holds the write: the decision starts after it, no two peeks at once', async ($, on) => {
  let calls: ReturnType<typeof seat> | null = null
  const { w, seen } = sleepingPeek(STATE_FULL, {}, () => calls!.clock.sleep(1000))
  calls = seat(on, w)
  await startSession(calls, $)
  const ui = await mountPane($, 'desktop')
  // Someone else's rebuild moved since.from: the timer tick calls a re-anchor (peek), and it sleeps.
  w.files[STATE] = JSON.stringify({ ...STATE_FULL, since: { ...STATE_FULL.since, from: '2026-10-20T10:00:00' } })
  w.mtime = 2
  await calls.clock.advance(15000)
  await calls.clock.settle()
  expect(seen.inFlight).toBe(1)
  await ui.press({ key: 'opt:d-fork:1' })
  await calls.clock.settle()
  expect((await ui.find({ key: 'busy:d-fork' }))?.text).toBe('saving…')
  expect(decisionRuns(calls.runs)).toHaveLength(0)
  await calls.clock.advance(1000)
  await calls.clock.settle()
  expect(decisionRuns(calls.runs)).toHaveLength(1)
  expect(decisionAfterPeek(calls.runs)).toBe(true)
  await calls.clock.advance(1000)
  await calls.clock.settle()
  expect(seen.max).toBe(1)
})

test('a "Refresh" peek holds the write: the decision starts after it, no two peeks at once', async ($, on) => {
  let calls: ReturnType<typeof seat> | null = null
  // `nod status` fails at the start: loadError shows "Refresh", the snapshot is fresh — the write buttons are there.
  const { w, seen } = sleepingPeek(STATE_FULL, {
    run: argv => (argv.includes('status') ? { exitCode: 3, stderr: 'error: network\n' } : {}),
  }, () => calls!.clock.sleep(1000))
  calls = seat(on, w)
  await startSession(calls, $)
  const ui = await mountPane($, 'desktop')
  await ui.press({ key: 'refresh' })
  await calls.clock.settle()
  expect(seen.inFlight).toBe(1)
  await ui.press({ key: 'opt:d-fork:1' })
  await calls.clock.settle()
  expect((await ui.find({ key: 'busy:d-fork' }))?.text).toBe('saving…')
  expect(decisionRuns(calls.runs)).toHaveLength(0)
  await calls.clock.advance(1000)
  await calls.clock.settle()
  expect(decisionRuns(calls.runs)).toHaveLength(1)
  expect(decisionAfterPeek(calls.runs)).toBe(true)
  await calls.clock.advance(1000)
  await calls.clock.settle()
  expect(seen.max).toBe(1)
})

/**
 * A world with a core without an inter-process lock: a nod process reads the store (`store`) at the start and writes
 * state.json at the end. So a process started before someone else's write rewrites the file with old data. Counts all
 * nod processes in flight (except the `--help` probe). `sleeps` — how long a process sleeps by its kind of argv.
 */
const coreWorld = (sleeps: { decision?: number; peek?: number; status?: number }, statusFails = false) => {
  const seen = { inFlight: 0, max: 0, order: [] as string[] }
  let store: Snapshot = STATE_FULL
  let clock: Calls['clock'] | null = null
  const w = world(STATE_FULL)
  const kind = (argv: readonly string[]) =>
    (argv.includes('decision') ? 'decision' : argv.includes('--peek') ? 'peek' : argv.includes('status') ? 'status' : null)
  w.run = async argv => {
    const k = kind(argv)
    if (k === null) return {}
    seen.inFlight += 1
    seen.max = Math.max(seen.max, seen.inFlight)
    seen.order.push(k + ':start')
    const read = k === 'decision' ? { ...store, waiting: store.waiting.filter(x => x.id !== argv.at(-2)) } : store
    const ms = sleeps[k] ?? 0
    if (ms > 0) await clock!.sleep(ms)
    store = read
    w.files[STATE] = JSON.stringify(read)
    w.mtime = (w.mtime ?? 1) + 1
    seen.order.push(k + ':end')
    seen.inFlight -= 1

    return k === 'status' && statusFails ? { exitCode: 3, stderr: 'error: network\n' } : {}
  }

  return { w, seen, bind: (c: Calls) => { clock = c.clock } }
}

const startsAfterEnd = (order: string[], first: string, then: string) =>
  order.indexOf(then + ':start') > order.indexOf(first + ':end') && order.indexOf(first + ':end') >= 0

test('a timer peek during a write waits for its end; the screen shows the written file', async ($, on) => {
  const { w, seen, bind } = coreWorld({ decision: 20000, peek: 500 })
  const calls = seat(on, w)
  bind(calls)
  await startSession(calls, $)
  const ui = await mountPane($, 'desktop')
  await ui.press({ key: 'opt:d-fork:1' })
  await calls.clock.settle()
  // Someone else's rebuild moved since.from: the 15 s timer tick asks for a re-anchor while the write still runs.
  w.files[STATE] = JSON.stringify({ ...STATE_FULL, since: { ...STATE_FULL.since, from: '2026-10-20T10:00:00' } })
  w.mtime = (w.mtime ?? 1) + 1
  await calls.clock.advance(15000)
  await calls.clock.settle()
  expect(seen.order.filter(x => x === 'peek:start')).toHaveLength(0)
  await calls.clock.advance(5000)
  await calls.clock.settle()
  for (let i = 0; i < 4; i += 1) {
    await calls.clock.advance(500)
    await calls.clock.settle()
  }
  expect(startsAfterEnd(seen.order, 'decision', 'peek')).toBe(true)
  expect(seen.max).toBe(1)
  expect(await ui.find({ key: 'dec:d-fork' })).toBeUndefined()
})

test('"Refresh" during a write waits for its end; the screen shows the written file', async ($, on) => {
  const { w, seen, bind } = coreWorld({ decision: 1000, peek: 500 }, true)
  const calls = seat(on, w)
  bind(calls)
  await startSession(calls, $)
  const ui = await mountPane($, 'desktop')
  await ui.press({ key: 'opt:d-fork:1' })
  await calls.clock.settle()
  await ui.press({ key: 'refresh' })
  await calls.clock.settle()
  expect(seen.order.filter(x => x === 'peek:start')).toHaveLength(0)
  for (let i = 0; i < 6; i += 1) {
    await calls.clock.advance(500)
    await calls.clock.settle()
  }
  expect(startsAfterEnd(seen.order, 'decision', 'peek')).toBe(true)
  expect(seen.max).toBe(1)
  expect(await ui.find({ key: 'dec:d-fork' })).toBeUndefined()
})

test('a click while the start nod status runs waits for its end; "saving…" at once', async ($, on) => {
  on('tool.call', () => ({ result: {} }))
  const { w, seen, bind } = coreWorld({ status: 1000 })
  const calls = seat(on, w)
  bind(calls)
  await startSession(calls, $)
  // A snapshot without the core: tool.call rereads the file while the start status still sleeps.
  await $.tool.call({ tool: 'mcp__t__x' })
  await calls.clock.settle()
  const ui = await mountPane($, 'desktop')
  await ui.press({ key: 'opt:d-fork:1' })
  await calls.clock.settle()
  expect((await ui.find({ key: 'busy:d-fork' }))?.text).toBe('saving…')
  expect(seen.order.filter(x => x === 'decision:start')).toHaveLength(0)
  await calls.clock.advance(1000)
  await calls.clock.settle()
  expect(startsAfterEnd(seen.order, 'status', 'decision')).toBe(true)
  expect(seen.max).toBe(1)
})

test('the second write waits for the background peek of the first; no two peeks at once', async () => {
  const journal: string[] = []
  const peeks: (() => void)[] = []
  let inFlight = 0
  let maxInFlight = 0
  function cellOf<T>(name: string, value: T): Cell<T> & { value: T } {
    const c = {
      value,
      read: async () => c.value,
      write: async (v: T) => { journal.push(`${name}.write(${String(v)})`); c.value = v },
    }

    return c
  }
  const st = {
    stateDir: cellOf<string | null>('stateDir', DIR), nodPrefix: cellOf<readonly string[] | null | 'unknown'>('nodPrefix', ['nod']),
    snapshot: cellOf('snapshot', null), loadError: cellOf<string | null>('loadError', null), lastMtime: cellOf('lastMtime', 0),
    sinceFrom: cellOf<string | null>('sinceFrom', null), pending: cellOf<string | null>('pending', null),
    progress: cellOf('progress', null), writeError: cellOf('writeError', null), draft: cellOf('draft', ''),
    expanded: cellOf<string[]>('expanded', []), freeFor: cellOf<string | null>('freeFor', null),
  }
  const done = { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
  const $ = {
    plugin: { root: 'D:/mod' },
    process: {
      run: async (argv: readonly string[]) => {
        journal.push('process.run ' + argv.slice(3).join(' '))
        if (!argv.includes('--peek')) return done
        inFlight += 1
        maxInFlight = Math.max(maxInFlight, inFlight)
        await new Promise<void>(resolve => peeks.push(resolve))
        inFlight -= 1

        return done
      },
    },
    fs: { stat: async () => { throw new Error('no file') }, read: async () => '' },
    ui: { log: async () => undefined, invalidate: () => undefined },
  }
  const tick = () => new Promise(resolve => setTimeout(resolve, 20))
  const a = makeActions($ as never, st as unknown as PaneState)
  a.answer('d-fork', 'A')
  await tick()
  expect(peeks).toHaveLength(1)
  a.answer('d-ver2', 'accept')
  await tick()
  expect(local.pending).toBe('d-ver2')
  expect(journal.some(x => x.includes('d-ver2 accept'))).toBe(false)
  peeks[0]()
  await tick()
  const peekDone = journal.findIndex(x => x.startsWith('process.run status --peek'))
  const second = journal.indexOf('process.run decision answer -- d-ver2 accept')
  expect(second).toBeGreaterThan(peekDone)
  expect(peeks).toHaveLength(2)
  peeks[1]()
  await tick()
  expect(maxInFlight).toBe(1)
  expect(local.pending).toBeNull()
})

test('"all" on a stale snapshot does not mark a press: no false "render after click"', async () => {
  renderLines(Date.now(), 'reset')
  const st = { snapshot: cell(STATE_STALE) }
  makeActions({ ui: { log: async () => undefined } } as never, st as unknown as PaneState).answerAll()
  await new Promise(resolve => setTimeout(resolve, 20))
  expect(renderLines(Date.now(), null)).toEqual([])
})

test('the id and the answer go after "--": the core does not take an answer "-h" for a flag', () => {
  expect(answerArgs('d-fork', '-h', { free: true })).toEqual(['decision', 'answer', '--free', '--', 'd-fork', '-h'])
  expect(answerArgs('d-ver2', 'return', { note: 'no button' }))
    .toEqual(['decision', 'answer', '--note', 'no button', '--', 'd-ver2', 'return'])
})

test('a state refusal in "all", in expanding and in an own answer goes to the debug log, not to an uncaught promise', async () => {
  const logs: string[] = []
  const broken = (what: string) => ({
    read: async () => { throw new Error(what + ' does not read') },
    write: async () => { throw new Error(what + ' does not write') },
  })
  const st = { snapshot: broken('snapshot'), expanded: broken('expanded'), freeFor: broken('freeFor') }
  const $ = {
    ui: { log: async (text: string, o?: { to?: string }) => { if (o?.to === 'debug') logs.push(text) } },
  }
  const a = makeActions($ as never, st as unknown as PaneState)
  a.answerAll()
  a.toggle('d-ver2')
  a.openFree('d-fork')
  await new Promise(resolve => setTimeout(resolve, 20))
  expect(logs.sort()).toEqual([
    'nod: expanded does not read',
    'nod: freeFor does not write',
    'nod: snapshot does not read',
  ])
})
