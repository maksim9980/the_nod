import { test, expect } from 'claude-code/testing'
import { ROOT, STATE, STATE_FULL } from './fixtures'
import { mountPane, seat, startSession } from './harness'
import { candidates, coreMain } from '../hooks/nod'

const nodCommand = ($: Parameters<Parameters<typeof test>[1]>[0]) =>
  $.command.run({ command: 'nod', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 } })

const isProbe = (argv: readonly string[]) => argv.at(-1) === '--help'

test('the default candidate is the __main__.py file from the plugin root, before nod from PATH', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' }, pythonCore: true })
  await startSession(calls, $)
  const probes = calls.runs.filter(isProbe)
  expect(probes[0]?.slice(0, 2)).toEqual(['python', '-P'])
  expect(probes[0]?.[2]).toMatch(/[\\/]the_nod[\\/]__main__\.py$/)
  expect(probes.length).toBe(1)
  expect((await nodCommand($)).text).toContain('\nnod: python -P ' + probes[0]?.[2])
})

test('the order of the candidates: own command, python, python3, py, nod', () => {
  const main = coreMain('/opt/nod')
  expect(candidates('/opt/nod', '')).toEqual([
    ['python', '-P', main], ['python3', '-P', main], ['py', '-3', '-P', main], ['nod'],
  ])
  expect(candidates('/opt/nod', ' my-core  --flag ')).toEqual([
    ['my-core', '--flag'], ['python', '-P', main], ['python3', '-P', main], ['py', '-3', '-P', main], ['nod'],
  ])
})

test('empty userConfig: python, python3, py, nod — in order, until one answers', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' }, pythonCore: true, run: argv => ({ exitCode: isProbe(argv) && argv[0] !== 'nod' ? 1 : 0 }) })
  await startSession(calls, $)
  expect(calls.runs.filter(isProbe).map(a => a[0])).toEqual(['python', 'python3', 'py', 'nod'])
  expect((await nodCommand($)).text).toContain('\nnod: nod')
})

test('python answers with code 9009, no python3, no py — nod from PATH is taken', async ($, on) => {
  const store = (argv: readonly string[]) => argv[0] === 'python' ? { exitCode: 9009, stderr: 'Python was not found; run without arguments to install' } : argv[0] === 'python3' || argv[0] === 'py' ? { deny: 'ENOENT' } : { exitCode: 0 }
  const calls = seat(on, { files: { [STATE]: '{}' }, pythonCore: true, run: argv => isProbe(argv) ? store(argv) : { exitCode: 0 } })
  await startSession(calls, $)
  expect(calls.runs.filter(isProbe).map(a => a[0])).toEqual(['python', 'python3', 'py', 'nod'])
  expect((await nodCommand($)).text).toContain('\nnod: nod')
})

// macOS and stock Ubuntu: there is `python3` only, no `python`, no `py`.
const onlyPython3 = (argv: readonly string[]) =>
  isProbe(argv) && argv[0] !== 'python3' ? { deny: 'ENOENT' } : { exitCode: 0 }

test('a machine with python3 only: the pane finds the core through python3', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' }, pythonCore: true, run: onlyPython3 })
  await startSession(calls, $)
  const probes = calls.runs.filter(isProbe)
  expect(probes.map(a => a[0])).toEqual(['python', 'python3'])
  expect(probes[1]?.slice(0, 2)).toEqual(['python3', '-P'])
  expect(probes[1]?.[2]).toMatch(/[\\/]the_nod[\\/]__main__\.py$/)
  expect((await nodCommand($)).text).toContain('\nnod: python3 -P ' + probes[1]?.[2])
})

test('a machine with python3 only: a write goes through python3 -P __main__.py', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1, pythonCore: true, run: onlyPython3 })
  await startSession(calls, $)
  const ui = await mountPane($, 'desktop')
  await ui.press({ key: 'opt:d-fork:1' })
  await calls.clock.settle()
  const answer = calls.runs.find(a => a.includes('decision'))!
  expect(answer.slice(0, 2)).toEqual(['python3', '-P'])
  expect(answer[2]).toMatch(/the_nod[\\/]__main__\.py$/)
  expect(answer.slice(-5)).toEqual(['decision', 'answer', '--', 'd-fork', 'Local format'])
})

test('userConfig.core is tried first', { options: { core: 'py -3.13 -m the_nod' } }, async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' } })
  await startSession(calls, $)
  expect(calls.runs.filter(isProbe)).toEqual([['py', '-3.13', '-m', 'the_nod', '--help']])
  expect((await nodCommand($)).text).toContain('\nnod: py -3.13 -m the_nod')
})

test('nobody answered — "Python 3.13 is needed" and a line per candidate', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' }, pythonCore: true, run: argv => isProbe(argv) ? (argv[0] === 'python' ? { exitCode: 9009, stderr: 'Python was not found' } : { deny: 'ENOENT' }) : { exitCode: 0 } })
  await startSession(calls, $)
  const text = (await nodCommand($)).text ?? ''
  expect(text).toContain('\nnod not found: Python 3.13 is needed')
  expect(text).toContain('\n  python -P ')
  expect(text).toContain('\n  python3 -P ')
  expect(text).toContain(' — code 9009: Python was not found')
  expect(text).toContain('\n  nod --help — does not start')
})

test('without a state nod is not probed, the answer has no nod line', async ($, on) => {
  const calls = seat(on, { files: {} })
  await startSession(calls, $, 'D:\\x\\other')
  expect(calls.runs.filter(isProbe)).toEqual([])
  expect((await nodCommand($)).text).not.toContain('\nnod')
})

test('a refused ui.open does not stop finding nod', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' }, openDeny: 'no surface', pythonCore: true })
  await startSession(calls, $)
  expect((await nodCommand($)).text).toContain('\nnod: python -P ')
})

test('the probes run from the plugin root, not from the project folder', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' } })
  await startSession(calls, $)
  const cwd = calls.cwds[calls.runs.findIndex(isProbe)]
  expect(cwd).toBeDefined()
  expect(cwd?.startsWith(ROOT)).toBe(false)
})

test('coreMain: a root with spaces and non-ASCII letters, a root with "/"', () => {
  expect(coreMain('D:\\My Projects\\Nød')).toBe('D:\\My Projects\\Nød\\the_nod\\__main__.py')
  expect(coreMain('/home/u/nod')).toBe('/home/u/nod/the_nod/__main__.py')
})

test('a write with the python -P core: decision answer goes through __main__.py', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1, pythonCore: true })
  await startSession(calls, $)
  const ui = await mountPane($, 'desktop')
  await ui.press({ key: 'opt:d-fork:1' })
  await calls.clock.settle()
  const answer = calls.runs.find(a => a.includes('decision'))!
  expect(answer.slice(0, 2)).toEqual(['python', '-P'])
  expect(answer[2]).toMatch(/the_nod[\\/]__main__\.py$/)
  expect(answer.slice(-5)).toEqual(['decision', 'answer', '--', 'd-fork', 'Local format'])
})
