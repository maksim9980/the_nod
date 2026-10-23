// Three channels of a press: status, transcript and toast are set synchronously before any await; outcomes go to
// the status and the transcript, the toast only for an error and a skip. Transcript and toast speak only with `diag` on (off by default).
import { test, expect } from 'claude-code/testing'
import { setDiag } from '../hooks/report'
import { local } from '../hooks/local'
import { makeActions } from '../hooks/actions'
import type { Cell, PaneState } from '../hooks/state'
import { DIR, STATE, STATE_FULL } from './fixtures'
import { mountPane, runNod, seat, startSession } from './harness'
import type { World } from './harness'

const NOW = Date.parse('2026-10-20T10:12:00')
const world = (extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1, now: NOW, ...extra })
const OTHER = 'C:\\Users\\owner\\.claude\\dev-mods\\0a1b2c3d\\nod-pane'
const PRESSED = 'pressed “Local format”'
const ANSWER = runNod(['decision', 'answer', '--', 'd-fork', 'Local format'])

type StateEvent = { key: string }
type Next = (e: StateEvent) => Promise<{ value?: { value?: unknown; version?: number } }>

for (const surface of ['desktop', 'terminal'] as const) {
  test(`(c) a press — status, transcript and toast "pressed …"; the outcome — status and transcript on ${surface}`, { options: { diag: true } }, async ($, on) => {
    const calls = seat(on, world())
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-fork:1' })
    await calls.clock.settle()
    expect(calls.statuses).toContain('Nod: ' + PRESSED + '…')
    expect(calls.transcript.some(l => l.startsWith('Nod: ' + PRESSED))).toBe(true)
    expect(calls.toasts.some(l => l.includes(PRESSED))).toBe(true)
    // The press is the first event of a click: before the decision run and before any outcome.
    const pressed = calls.events.findIndex(x => x.startsWith('toast:') && x.includes(PRESSED))
    expect(pressed).toBeLessThan(calls.events.findIndex(x => x.startsWith('run:') && x.includes('decision')))
    expect(calls.transcript.filter(l => /^Nod: saved d-fork · \d+ ms$/.test(l))).toHaveLength(1)
    // A success is not repeated as a toast.
    expect(calls.toasts.filter(l => l.includes('saved'))).toEqual([])
  })

  test(`(c) a refused write — toast and transcript "not saved" on ${surface}`, { options: { diag: true } }, async ($, on) => {
    const calls = seat(on, world({ run: argv => (argv.includes('decision') ? { deny: 'denied' } : {}) }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'opt:d-fork:1' })
    await calls.clock.settle()
    expect(calls.transcript.filter(l => l.startsWith('Nod: not saved d-fork — '))).toHaveLength(1)
    expect(calls.toasts.filter(l => l.startsWith('Nod: not saved d-fork — '))).toHaveLength(1)
  })

  test(`(b) a foreign instance of another root after the start: the pane draws with the double-load line, a click writes on ${surface}`, { options: { diag: true } }, async ($, on) => {
    let foreign = false
    on('state.get', (async (_: unknown, e: StateEvent, next: Next) => {
      const real = await next(e)

      return foreign && e.key === 'instance' ? { ...real, value: { ...real.value, value: 'zzz@' + OTHER } } : real
    }) as never)
    const calls = seat(on, world())
    await startSession(calls, $)
    foreign = true
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'dec:d-fork' })).toBeDefined()
    expect((await ui.find({ key: 'double-load' }))?.text).toContain(OTHER)
    expect(calls.transcript.some(l => l.includes('the pane is recorded for another instance: zzz@' + OTHER))).toBe(true)
    await ui.press({ key: 'opt:d-fork:1' })
    await calls.clock.settle()
    expect(calls.runs.filter(r => r.includes('decision'))).toEqual([ANSWER])
  })
}

test('(c) diag: false — only the status, transcript and toast are silent', { options: { diag: false } }, async ($, on) => {
  const calls = seat(on, world())
  await startSession(calls, $)
  const ui = await mountPane($, 'desktop')
  await ui.press({ key: 'opt:d-fork:1' })
  await calls.clock.settle()
  expect(calls.statuses).toContain('Nod: ' + PRESSED + '…')
  expect(calls.runs.filter(r => r.includes('decision'))).toEqual([ANSWER])
  expect(calls.transcript.filter(l => l.includes('pressed') || l.includes('saved'))).toEqual([])
  expect(calls.toasts).toEqual([])
})

// Early exits — through the module directly: a fake `$` and state, a journal of the channels.
const done = { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
const tick = () => new Promise(resolve => setTimeout(resolve, 20))

function cell<T>(value: T): Cell<T> & { value: T } {
  const c = { value, read: async () => c.value, write: async (v: T) => { c.value = v } }

  return c
}

function fakeState(over: Partial<Record<keyof PaneState, unknown>> = {}): PaneState {
  return {
    stateDir: cell<string | null>(DIR), nodPrefix: cell<readonly string[] | null | 'unknown'>(['nod']),
    snapshot: cell<unknown>(STATE_FULL), loadError: cell<string | null>(null), lastMtime: cell(0),
    sinceFrom: cell<string | null>(null), draft: cell(''), expanded: cell<string[]>([]),
    freeFor: cell<string | null>(null), instance: cell<string | null>(null), otherRoot: cell<string | null>(null),
    ...Object.fromEntries(Object.entries(over).map(([k, v]) => [k, cell(v)])),
  } as unknown as PaneState
}

function fakeEngine(journal: string[], hold?: { wait: Promise<void> }) {
  return {
    plugin: { root: 'D:/mod' },
    process: {
      run: async (argv: readonly string[]) => {
        journal.push('run ' + argv.slice(3).join(' '))
        if (hold !== undefined && argv.includes('decision')) await hold.wait

        return done
      },
    },
    fs: { stat: async () => { throw new Error('no file') }, read: async () => '' },
    ui: {
      log: (text: string, o?: { to?: string }) => { if (o?.to !== 'debug') journal.push('log ' + text) },
      toast: (text: string) => { journal.push('toast ' + text) },
      invalidate: () => undefined,
      status: (text: string | undefined) => { journal.push('status ' + String(text)) },
    },
    clock: { after: () => ({ cancel: () => undefined }) },
  }
}

/** A skip is heard in all three channels and lies in the footer. */
function expectIgnored(journal: string[], reason: string | RegExp): void {
  const hit = (prefix: string) => journal.some(x => {
    const text = x.slice(prefix.length)

    return x.startsWith(prefix) && (typeof reason === 'string'
      ? text === 'Nod: ignored — ' + reason
      : reason.test(text))
  })
  expect(hit('status ')).toBe(true)
  expect(hit('log ')).toBe(true)
  expect(hit('toast ')).toBe(true)
  expect(local.lastAction?.result).toBe('ignored')
}

test('(e0) three channels synchronously, before the first await: status, transcript, toast', async () => {
  setDiag(true)  // the transcript and the toast are off by default
  const journal: string[] = []
  makeActions(fakeEngine(journal) as never, fakeState()).answer('d-fork', 'A')
  expect(journal.slice(0, 3).map(x => x.split(' ')[0])).toEqual(['status', 'log', 'toast'])
  expect(journal.slice(0, 3).every(x => x.includes('pressed “A”'))).toBe(true)
  // The write lock is a module one: the next test must not find it held.
  await tick()
})

test('(d) busy held: "ignored — saving d-fork since HH:MM:SS" in all channels', async () => {
  setDiag(true)  // the transcript and the toast are off by default
  const journal: string[] = []
  let free: () => void = () => undefined
  const hold = { wait: new Promise<void>(resolve => { free = resolve }) }
  const a = makeActions(fakeEngine(journal, hold) as never, fakeState())
  a.answer('d-fork', 'A')
  await tick()
  a.answer('d-ver2', 'accept')
  await tick()
  expectIgnored(journal, /^Nod: ignored — saving d-fork since \d\d:\d\d:\d\d$/)
  free()
  await tick()
})

test('(d) nod not found: a skip with the reason, nod is not called', async () => {
  setDiag(true)  // the transcript and the toast are off by default
  const journal: string[] = []
  makeActions(fakeEngine(journal) as never, fakeState({ nodPrefix: null })).answer('d-fork', 'A')
  await tick()
  expectIgnored(journal, 'nod not found: Python 3.13 is needed (python.org), python, python3 or py in PATH; restart the session after installing')
  expect(journal.some(x => x.startsWith('run '))).toBe(false)
  expect(local.pending).toBeNull()
})

test('(d) a stale snapshot: a skip for one answer and for "all"', async () => {
  setDiag(true)  // the transcript and the toast are off by default
  const journal: string[] = []
  const a = makeActions(fakeEngine(journal) as never, fakeState({ snapshot: { ...STATE_FULL, fresh: false } }))
  a.answer('d-fork', 'A')
  await tick()
  expectIgnored(journal, 'snapshot not fresh')
  journal.length = 0
  a.answerAll()
  await tick()
  expectIgnored(journal, 'snapshot not fresh')
  expect(journal.some(x => x.startsWith('run '))).toBe(false)
})

// The header and /nod: they show whether the pane is redrawn and what the module knows.
const renderNo = (text: string | undefined): number => Number(/ · #(\d+)$/.exec(text ?? '')?.[1] ?? NaN)
const nodAnswer = async ($: Parameters<Parameters<typeof test>[1]>[0]) => (await $.command.run({
  command: 'nod', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 },
} as never) as { text?: string }).text ?? ''

for (const surface of ['desktop', 'terminal'] as const) {
  test(`(e) header: "drawn HH:MM:SS · #N", the number grew after a press on ${surface}`, async ($, on) => {
    const calls = seat(on, world())
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    const before = (await ui.find({ key: 'header' }))?.text
    expect(before).toMatch(/ · drawn 10:12:00 · #\d+$/)
    await ui.press({ key: 'opt:d-fork:1' })
    await calls.clock.settle()
    expect(renderNo((await ui.find({ key: 'header' }))?.text)).toBeGreaterThan(renderNo(before))
  })
}

test('(f) /nod — instance, owner, pending, last action, number of drawings', async ($, on) => {
  const calls = seat(on, world())
  await startSession(calls, $)
  const ui = await mountPane($, 'desktop')
  const shown = renderNo((await ui.find({ key: 'header' }))?.text)
  const text = await nodAnswer($)
  expect(text).toMatch(/\ninstance [0-9a-z]+ · root .+/)
  expect(text).toContain('\npane owner: this instance')
  expect(text).toContain('\npending: —')
  expect(text).toContain('\nlast action: —')
  const renders = Number(/\nrenders: (\d+) · last \d\d:\d\d:\d\d/.exec(text)?.[1] ?? NaN)
  expect(renders).toBeGreaterThanOrEqual(shown)
})

test('(f) /nod answers when $.state does not: the module lines are in place', async ($, on) => {
  let hang = false
  let calls: ReturnType<typeof seat> | null = null
  on('state.get', (async (_: unknown, e: StateEvent, next: Next) => {
    if (hang) await calls!.clock.sleep(60000)

    return next(e)
  }) as never)
  calls = seat(on, world())
  await startSession(calls, $)
  hang = true
  const answer = nodAnswer($)
  await calls.clock.advance(5000)
  await calls.clock.settle()
  const text = await answer
  expect(text).toContain('pane state does not respond')
  expect(text).toContain('\npending: —')
  expect(text).toMatch(/\nrenders: \d+/)
  hang = false
  await calls.clock.advance(60000)
  await calls.clock.settle()
})
