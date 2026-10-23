// Resilience to hangs: a stuck write lock and an endless core-lock slot.
// A file of its own: the tests leave the module lock held longer than their end.
import { local } from '../hooks/local'
import { test, expect } from 'claude-code/testing'
import { DIR, STATE, STATE_FULL } from './fixtures'
import { mountPane, seat, startSession } from './harness'
import { STUCK_AFTER_MS, backdateLockForTest, makeActions } from '../hooks/actions'
import type { Cell, LastAction, PaneState } from '../hooks/state'

const done = { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
const tick = () => new Promise(resolve => setTimeout(resolve, 20))

function fakeState(journal: string[]) {
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
  }
}

test('(f) a stuck lock: a new click resets it and writes; the slot is awaited no longer than 70 s', async () => {
  const journal: string[] = []
  const timers: { ms: number; fn: () => void }[] = []
  let free: () => void = () => undefined
  const hang = new Promise<void>(resolve => { free = resolve })
  const $ = {
    plugin: { root: 'D:/mod' },
    process: {
      run: async (argv: readonly string[]) => {
        journal.push('process.run ' + argv.slice(3).join(' '))
        if (argv.includes('d-fork')) {
          await hang
          // The hung write finally came back — with an error: its writeError and outcome belong to nobody now.
          return { ...done, exitCode: 3, stderr: 'error: too late\n' }
        }
        return done
      },
    },
    fs: { stat: async () => { throw new Error('no file') }, read: async () => '' },
    ui: { log: async () => undefined, invalidate: () => undefined, status: (t?: string) => { journal.push('status ' + String(t)) } },
    clock: { after: (ms: number, fn: () => void) => { timers.push({ ms, fn }); return { cancel: () => undefined } } },
  }
  const st = fakeState(journal)
  const a = makeActions($ as never, st as unknown as PaneState)
  try {
    a.answer('d-fork', 'A')
    await tick()
    expect(journal).toContain('process.run decision answer -- d-fork A')
    // The threshold from the constants: CORE_WAIT_MS + 2 · NOD_TIMEOUT_MS + 10 s = 200 s; the lock is 10 s older.
    expect(STUCK_AFTER_MS).toBe(200000)
    backdateLockForTest(STUCK_AFTER_MS + 10000)
    a.answer('d-ver2', 'accept')
    await tick()
    expect(local.lastAction!.detail).toBe('reset a stuck lock (210 s)')
    expect(local.pending).toBe('d-ver2')
    // The slot is still held by the hung d-fork: the wait is bounded by a 70 s timer.
    expect(journal.some(x => x.includes('d-ver2 accept'))).toBe(false)
    for (const t of timers.filter(x => x.ms === 70000)) t.fn()
    await tick()
    expect(journal).toContain('status Nod: the snapshot rebuild did not finish in 70 s, saving')
    expect(journal).toContain('process.run decision answer -- d-ver2 accept')
    expect(local.lastAction).toMatchObject({
      what: 'answer d-ver2', result: 'ok',
      detail: 'reset a stuck lock (210 s) · the snapshot rebuild did not finish in 70 s, saving',
    })
    expect(local.pending).toBeNull()
  } finally {
    free()
    await tick()
  }
  // The hung write, when it finally came back, touches neither pending, nor writeError, nor the footer, nor the status.
  expect(local.pending).toBeNull()
  expect(local.writeError).toBeNull()
  expect(local.lastAction).toMatchObject({ what: 'answer d-ver2', result: 'ok' })
  expect(journal.filter(x => x.startsWith('status') && x.includes('d-fork') && !x.includes('pressed'))).toEqual([
    'status Nod: saving d-fork…',
  ])
  expect(journal.filter(x => x.startsWith('process.run status --peek')).length).toBe(1)
})

test('an error after a lock reset: the notes of the way first in the detail, then the reason', async () => {
  const journal: string[] = []
  const timers: { ms: number; fn: () => void }[] = []
  let free: () => void = () => undefined
  const hang = new Promise<void>(resolve => { free = resolve })
  const $ = {
    plugin: { root: 'D:/mod' },
    process: {
      run: async (argv: readonly string[]) => {
        if (argv.includes('d-fork')) await hang
        if (argv.includes('d-ver2')) return { ...done, exitCode: 3, stderr: 'error: state not fresh\n' }
        return done
      },
    },
    fs: { stat: async () => { throw new Error('no file') }, read: async () => '' },
    ui: { log: async () => undefined, invalidate: () => undefined, status: () => undefined },
    clock: { after: (ms: number, fn: () => void) => { timers.push({ ms, fn }); return { cancel: () => undefined } } },
  }
  const st = fakeState(journal)
  const a = makeActions($ as never, st as unknown as PaneState)
  a.answer('d-fork', 'A')
  await tick()
  backdateLockForTest(STUCK_AFTER_MS + 10000)
  a.answer('d-ver2', 'accept')
  await tick()
  for (const t of timers.filter(x => x.ms === 70000)) t.fn()
  await tick()
  expect(local.lastAction).toMatchObject({
    what: 'answer d-ver2', result: 'error',
    detail: 'reset a stuck lock (210 s) · the snapshot rebuild did not finish in 70 s, saving · state not fresh',
  })
  free()
  await tick()
  expect(local.lastAction).toMatchObject({ what: 'answer d-ver2', result: 'error' })
})

test('a click while the start nod status hangs: "waiting for the snapshot rebuild…" after 1 s, the write after 70 s', async ($, on) => {
  const w = { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1, now: Date.parse('2026-10-20T10:12:00') }
  const calls = seat(on, {
    ...w,
    run: async argv => {
      if (argv.includes('status') && !argv.includes('--peek')) await calls.clock.sleep(200000)

      return {}
    },
  })
  on('tool.call', () => ({ result: {} }))
  await startSession(calls, $)
  // A snapshot without the core: tool.call rereads the file while the start status hangs.
  await $.tool.call({ tool: 'mcp__t__x' })
  await calls.clock.settle()
  const ui = await mountPane($, 'desktop')
  await ui.press({ key: 'opt:d-fork:0' })
  await calls.clock.settle()
  expect((await ui.find({ key: 'busy:d-fork' }))?.text).toBe('saving…')
  await calls.clock.advance(1000)
  await calls.clock.settle()
  expect(calls.statuses).toContain('Nod: waiting for the snapshot rebuild…')
  expect(calls.runs.filter(r => r.includes('decision'))).toHaveLength(0)
  await calls.clock.advance(69000)
  await calls.clock.settle()
  expect(calls.statuses).toContain('Nod: the snapshot rebuild did not finish in 70 s, saving')
  expect(calls.runs.filter(r => r.includes('decision'))).toHaveLength(1)
  await calls.clock.advance(200000)
  await calls.clock.settle()
})
