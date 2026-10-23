// Self-diagnosis without logs: the engine status line and the "last action" in the footer.
import { local } from '../hooks/local'
import { test, expect } from 'claude-code/testing'
import { DIR, STATE, STATE_FULL } from './fixtures'
import { mountPane, seat, startSession } from './harness'
import type { World } from './harness'
import { makeActions } from '../hooks/actions'
import type { Cell, LastAction, PaneState } from '../hooks/state'
import { EN } from '../hooks/texts/index'

const NOW = Date.parse('2026-10-20T10:12:00')

const world = (state: unknown, extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(state) }, mtime: 1, now: NOW, ...extra })

const withoutFork = { ...STATE_FULL, waiting: STATE_FULL.waiting.filter(x => x.id !== 'd-fork') }

test('the last action line: ok, error, ignored, running', () => {
  const base = { what: 'answer d-pcfd', at: 0, detail: '' }
  expect(EN.lastActionLine({ ...base, ms: 843, result: 'ok' })).toBe('last action: answer d-pcfd · 843 ms · ok')
  expect(EN.lastActionLine({ ...base, ms: 12, result: 'error', detail: 'could not start nod' }))
    .toBe('last action: answer d-pcfd · 12 ms · error: could not start nod')
  expect(EN.lastActionLine({ ...base, ms: null, result: 'ignored', detail: 'saving d-yyyy' }))
    .toBe('last action: answer d-pcfd · ignored: saving d-yyyy')
  expect(EN.lastActionLine({ ...base, ms: null, result: 'running' })).toBe('last action: answer d-pcfd · running')
})

for (const surface of ['desktop', 'terminal'] as const) {
  test(`after a successful write the footer: ok and d-fork; the status "saved", cleared after 5 s on ${surface}`, async ($, on) => {
    const w = world(STATE_FULL)
    w.run = argv => {
      if (argv.includes('decision')) {
        w.files[STATE] = JSON.stringify(withoutFork)
        w.mtime = 2
      }

      return {}
    }
    const calls = seat(on, w)
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'last-action' })).toBeUndefined()
    await ui.press({ key: 'opt:d-fork:0' })
    await calls.clock.settle()
    const line = (await ui.find({ key: 'last-action' }))?.text ?? ''
    expect(line).toMatch(/^last action: answer d-fork · \d+ ms · ok$/)
    expect(calls.statuses[0]).toBe('Nod: pressed “ISO”…')
    expect(calls.statuses).toContain('Nod: saving d-fork…')
    expect(calls.statuses.some(s => /^Nod: saved d-fork · \d+ ms$/.test(String(s)))).toBe(true)
    expect(calls.statuses.at(-1)).not.toBeUndefined()
    await calls.clock.advance(5000)
    await calls.clock.settle()
    expect(calls.statuses.at(-1)).toBeUndefined()
  })

  test(`a failed start: the footer "error", the status "not saved" stays on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, { run: argv => (argv.includes('decision') ? { deny: 'denied' } : {}) }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-fork:1' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'last-action' }))?.text)
      .toMatch(/^last action: answer d-fork · \d+ ms · error: could not start nod/)
    expect(String(calls.statuses.at(-1))).toMatch(/^Nod: not saved d-fork — could not start nod/)
    await calls.clock.advance(6000)
    await calls.clock.settle()
    expect(String(calls.statuses.at(-1))).toMatch(/^Nod: not saved d-fork/)
  })

  test(`(b) a click during a timer peek: "saving…" at once, "pressed" before the decision on ${surface}`, async ($, on) => {
    const w = world(STATE_FULL)
    const calls = seat(on, w)
    w.run = async argv => {
      if (argv.includes('--peek')) await calls.clock.sleep(1000)
      if (argv.includes('decision')) {
        w.files[STATE] = JSON.stringify(withoutFork)
        w.mtime = (w.mtime ?? 1) + 1
      }

      return {}
    }
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    // Someone else's rebuild moved since.from: the timer tick calls a re-anchor (peek), and it sleeps.
    w.files[STATE] = JSON.stringify({ ...STATE_FULL, since: { ...STATE_FULL.since, from: '2026-10-20T10:00:00' } })
    w.mtime = 2
    await calls.clock.advance(15000)
    await calls.clock.settle()
    await ui.press({ key: 'opt:d-fork:0' })
    expect((await ui.find({ key: 'busy:d-fork' }))?.text).toBe('saving…')
    await calls.clock.settle()
    const pressed = calls.events.indexOf('status:Nod: pressed “ISO”…')
    expect(pressed).toBeGreaterThanOrEqual(0)
    expect(calls.events.findIndex(x => x.startsWith('run:') && x.includes('decision'))).toBe(-1)
    await calls.clock.advance(1000)
    await calls.clock.settle()
    const decision = calls.events.findIndex(x => x.startsWith('run:') && x.includes('decision'))
    expect(decision).toBeGreaterThan(pressed)
    expect(await ui.find({ key: 'dec:d-fork' })).toBeUndefined()
    await calls.clock.advance(2000)
    await calls.clock.settle()
  })

  test(`"ignored" stays until the next press: the first send's outcome does not replace it on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, { submitDelay: 500 }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'backlog:pain' })
    await calls.clock.settle()
    await ui.press({ key: 'send' })
    await ui.press({ key: 'send' })
    await calls.clock.advance(500)
    await calls.clock.settle()
    const tail = calls.statuses.slice(calls.statuses.indexOf('Nod: ignored — sending in progress'))
    expect(tail).toEqual(['Nod: ignored — sending in progress'])
    await ui.press({ key: 'backlog:show' })
    await ui.press({ key: 'send' })
    await calls.clock.advance(500)
    await calls.clock.settle()
    expect(calls.statuses.at(-2)).toBe('Nod: pressed “Send”…')
    expect(String(calls.statuses.at(-1))).toMatch(/^Nod: send to chat — done · \d+ ms$/)
  })

  test(`the footer with the last action is drawn with an empty draft too; "Send" — ok on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'backlog:pain' })
    await ui.press({ key: 'send' })
    await calls.clock.settle()
    expect(await ui.find({ key: 'draft' })).toBeUndefined()
    expect((await ui.find({ key: 'last-action' }))?.text).toMatch(/^last action: send to chat · \d+ ms · ok$/)
  })
}

const done = { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false }

type Journal = { journal: string[]; st: PaneState & Record<string, Cell<unknown> & { value: unknown }> }

/** Fake state: every cell write is a journal line `<name>.write(...)`. */
function fakeState(journal: string[]): Journal['st'] {
  function cell<T>(name: string, value: T): Cell<T> & { value: T } {
    const c = {
      value,
      read: async () => c.value,
      write: async (v: T) => {
        journal.push(`${name}.write(${typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)})`)
        c.value = v
      },
    }

    return c
  }

  return {
    stateDir: cell<string | null>('stateDir', DIR), nodPrefix: cell<readonly string[] | null | 'unknown'>('nodPrefix', ['nod']),
    snapshot: cell('snapshot', null), loadError: cell<string | null>('loadError', null), lastMtime: cell('lastMtime', 0),
    sinceFrom: cell<string | null>('sinceFrom', null), pending: cell<string | null>('pending', null),
    progress: cell('progress', null), writeError: cell('writeError', null), draft: cell('draft', ''),
    expanded: cell<string[]>('expanded', []), freeFor: cell<string | null>('freeFor', null),
    lastAction: cell<LastAction | null>('lastAction', null),
  } as unknown as Journal['st']
}

/** Fake `$`: the status and the runs go to the same journal; `hold` holds the decision process until called. */
function fakeEngine(journal: string[], hold?: { wait: Promise<void> }) {
  return {
    plugin: { root: 'D:/mod' },
    process: {
      run: async (argv: readonly string[]) => {
        journal.push('process.run ' + argv.slice(3).join(' '))
        if (hold !== undefined && argv.includes('decision')) await hold.wait
        return done
      },
    },
    fs: { stat: async () => { throw new Error('no file') }, read: async () => '' },
    ui: {
      log: async () => undefined,
      invalidate: () => undefined,
      status: (text: string | undefined) => { journal.push('status ' + String(text)) },
    },
    clock: { after: () => ({ cancel: () => undefined }) },
  }
}

const tick = () => new Promise(resolve => setTimeout(resolve, 20))

test('(e) the "pressed" status is the first host call, "saving" before the decision run', async () => {
  const journal: string[] = []
  const st = fakeState(journal)
  makeActions(fakeEngine(journal) as never, st).answer('d-fork', 'A')
  // Synchronously, before the first await: the status, then pending in the module; $.state is untouched.
  expect(journal[0]).toBe('status Nod: pressed “A”…')
  expect(local.pending).toBe('d-fork')
  expect(journal.some(x => x.includes('.write('))).toBe(false)
  await tick()
  const run = journal.findIndex(x => x.startsWith('process.run decision'))
  expect(journal.indexOf('status Nod: saving d-fork…')).toBeGreaterThan(0)
  expect(journal.indexOf('status Nod: saving d-fork…')).toBeLessThan(run)
})

test('(d) a second click during a write: "ignored: saving d-fork" in the status and lastAction', async () => {
  const journal: string[] = []
  let free: () => void = () => undefined
  const hold = { wait: new Promise<void>(resolve => { free = resolve }) }
  const st = fakeState(journal)
  const a = makeActions(fakeEngine(journal, hold) as never, st)
  a.answer('d-fork', 'A')
  await tick()
  a.answer('d-ver2', 'accept')
  await tick()
  const ignoredLine = /^status Nod: ignored — saving d-fork since \d\d:\d\d:\d\d$/
  expect(journal.some(x => ignoredLine.test(x))).toBe(true)
  const last = local.lastAction as LastAction
  expect(last).toMatchObject({ what: 'answer d-ver2', result: 'ignored', ms: null })
  expect(EN.lastActionLine(last)).toMatch(/^last action: answer d-ver2 · ignored: saving d-fork since \d\d:\d\d:\d\d$/)
  free()
  await tick()
  expect(local.lastAction!.result).toBe('ok')
  expect(journal.filter(x => x.startsWith('process.run decision'))).toHaveLength(1)
  // "ignored" stays until the next press: "saved d-fork" did not replace it.
  expect(journal.filter(x => x.startsWith('status')).at(-1)).toMatch(ignoredLine)
})

test('a refused snapshot read in "all" and loadError in "Refresh" — lastAction "error", not an endless "running"', async () => {
  const journal: string[] = []
  const st = fakeState(journal)
  const broken = (what: string) => ({
    value: null,
    read: async () => { throw new Error(what + ' does not read') },
    write: async () => undefined,
  })
  ;(st as Record<string, unknown>).snapshot = broken('snapshot')
  ;(st as Record<string, unknown>).loadError = broken('loadError')
  const a = makeActions(fakeEngine(journal) as never, st)
  a.answerAll()
  await tick()
  expect(local.lastAction).toMatchObject({
    what: 'answer all', result: 'ignored', detail: 'pane state does not respond (snapshot: snapshot does not read)',
  })
  a.refresh()
  await tick()
  expect(local.lastAction).toMatchObject({
    what: 'snapshot refresh', result: 'error', detail: 'pane state does not respond (loadError: loadError does not read)',
  })
})

test('no silent exits: "Retry" without an error, "all" on a stale snapshot, an empty draft', async () => {
  const journal: string[] = []
  const st = fakeState(journal)
  st.snapshot.value = { ...STATE_FULL, fresh: false }
  const a = makeActions(fakeEngine(journal) as never, st)
  a.retry()
  await tick()
  expect(local.lastAction!.detail).toBe('nothing to retry')
  a.answerAll()
  await tick()
  expect(local.lastAction).toMatchObject({ what: 'answer all', result: 'ignored', detail: 'snapshot not fresh' })
  a.send()
  await tick()
  expect(local.lastAction).toMatchObject({ what: 'send to chat', result: 'ignored', detail: 'the draft is empty' })
  expect(journal.filter(x => x.startsWith('status Nod: ignored'))).toHaveLength(3)
})
