import { test, expect } from 'claude-code/testing'
import { DIR, ROOT, STATE } from './fixtures'
import { seat, startSession } from './harness'

const NOD_RUN = { command: 'nod', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 } } as const

test('finds .nod up from a subfolder and opens the pane', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' } })
  await startSession(calls, $, 'D:\\x\\proj\\src\\deep')
  expect(calls.opens.map(o => o.id)).toEqual(['nod'])
  expect(calls.runs.some(r => r[0] === 'git')).toBe(false)
})

test('a path with a space', async ($, on) => {
  const calls = seat(on, { files: { 'C:\\work\\tide pool\\.nod\\state.json': '{}' } })
  await startSession(calls, $, 'C:\\work\\tide pool\\app')
  expect(calls.opens).toHaveLength(1)
})

test('without a state — the pane does not open, /nod says where it looked', async ($, on) => {
  const calls = seat(on, { files: {} })
  await startSession(calls, $, 'D:\\x\\other')
  expect(calls.opens).toEqual([])
  const ran = await $.command.run(NOD_RUN)
  expect(ran.text?.split('\n')[0]).toBe('Nod: no state — no .nod/state.json in D:\\x\\other or above')
})

test('from a worktree takes the main worktree by git worktree list', async ($, on) => {
  const calls = seat(on, {
    files: { [STATE]: '{}' },
    run: argv => (argv[0] === 'git' ? { stdout: 'worktree D:/x/proj\nHEAD 0\nbranch refs/heads/2026-10-20\n\nworktree D:/x/wt\n' } : {}),
  })
  await startSession(calls, $, 'D:\\x\\wt\\sub')
  const at = calls.runs.findIndex(r => r[0] === 'git')
  expect(calls.runs[at]).toEqual(['git', '-C', 'D:\\x\\wt\\sub', 'worktree', 'list', '--porcelain'])
  expect(calls.cwds[at]?.startsWith(ROOT)).toBe(false)
  expect(calls.opens).toHaveLength(1)
  const ran = await $.command.run(NOD_RUN)
  expect(ran.text?.split('\n')[0]).toBe('Nod: pane opened · ' + DIR)
})

test('/nod opens the pane once more', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' } })
  await startSession(calls, $)
  const ran = await $.command.run(NOD_RUN)
  expect(calls.opens).toHaveLength(2)
  expect(ran.text?.split('\n')[0]).toBe('Nod: pane opened · ' + DIR)
})

test('a pane that was not placed says in the status how to open it', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' }, placed: false })
  await startSession(calls, $)
  expect(calls.opens).toHaveLength(1)
  expect(calls.statuses).toEqual(['Nod: /nod opens the pane'])
})

test('/nod with isPlaced: false says the pane is not placed, and why', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' }, placed: false, placeReason: 'width 90, 110 needed' })
  await startSession(calls, $)
  const ran = await $.command.run(NOD_RUN)
  const lines = ran.text?.split('\n') ?? []
  expect(lines[0]).toBe('Nod: the pane is not placed — width 90, 110 needed · ' + DIR)
  expect(lines[1]).toMatch(/^nod/)
})

test('a refused ui.open does not break the session start and /nod answers', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' }, openDeny: 'no surface' })
  await startSession(calls, $)
  const ran = await $.command.run(NOD_RUN)
  expect(ran.text).toContain('Nod: the pane did not open')
})
