import { test, expect } from 'claude-code/testing'
import { EN } from '../hooks/texts/index'
import { LEGACY_DIR } from '../hooks/find'
import { DIR, ROOT, STATE, STATE_FULL } from './fixtures'
import { mountPane, seat, startSession } from './harness'

const nodCommand = ($: Parameters<Parameters<typeof test>[1]>[0], args = '') =>
  $.command.run({ command: 'nod', args, origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 } })

/** State file of an older version in the project root. */
const LEGACY_STATE = ROOT + '\\' + LEGACY_DIR + '\\state.json'
const HINT = 'found ' + LEGACY_DIR + '/ from an older version: /nod migrate'

test('/nod init without a state: nod --root <cwd> init, then the pane and the snapshot', async ($, on) => {
  const files: Record<string, string> = {}
  const calls = seat(on, { files, run: argv => { if (argv.at(-1) === 'init') files[STATE] = '{}'; return { exitCode: 0, stdout: 'created ' + DIR } } })
  await startSession(calls, $)
  expect(calls.opens).toEqual([])
  const text = (await nodCommand($, 'init')).text ?? ''
  const init = calls.runs.find(a => a.at(-1) === 'init')!
  expect(init.slice(-3)).toEqual(['--root', ROOT, 'init'])
  expect(text).toContain('state created: ' + DIR)
  expect(calls.opens.length).toBe(1)
  expect(calls.runs.some(a => a.includes('status'))).toBe(true)
})

test('/nod init in a subfolder of a repository: --root is the root of the main worktree', async ($, on) => {
  const files: Record<string, string> = {}
  const cwd = ROOT + '\\sub'
  const calls = seat(on, { files, run: argv => {
    if (argv[0] === 'git' && argv[2] === cwd && argv.slice(3).join(' ') === 'worktree list --porcelain') return { stdout: 'worktree ' + ROOT + '\n' }
    if (argv.at(-1) === 'init') files[STATE] = '{}'

    return { exitCode: 0 }
  } })
  await startSession(calls, $, cwd)
  const text = (await nodCommand($, 'init')).text ?? ''
  expect(calls.runs.find(a => a.at(-1) === 'init')!.slice(-3)).toEqual(['--root', ROOT, 'init'])
  expect(text).toContain('state created: ' + DIR)
})

test('legacy state hint: no .nod, the older version folder up the tree — /nod suggests /nod migrate and opens the pane with it', async ($, on) => {
  const calls = seat(on, { files: { [LEGACY_STATE]: '{}' } })
  await startSession(calls, $, ROOT + '\\src')
  // A session start in such a folder opens nothing and probes no core: a repository that stays on the old tool is not nagged.
  expect(calls.opens).toEqual([])
  expect(calls.statuses).toEqual([])
  expect(calls.runs.some(a => a.at(-1) === '--help')).toBe(false)
  const text = (await nodCommand($)).text ?? ''
  expect(text.split('\n')[0]).toBe(HINT)
  expect(calls.opens.map(o => o.id)).toEqual(['nod'])
  const ui = await mountPane($, 'desktop')
  expect((await ui.find({ key: 'legacy' }))?.text).toBe(HINT)
  expect(await ui.find({ key: 'loading' })).toBeUndefined()
  expect(EN.legacyFound).toBe(HINT)
  expect((await nodCommand($, 'doctor')).text).toBe(HINT)
})

test('no .nod and no older version folder — "no state", the pane stays closed', async ($, on) => {
  const calls = seat(on, { files: {} })
  await startSession(calls, $, 'D:\\x\\other')
  expect(calls.opens).toEqual([])
  expect((await nodCommand($)).text?.split('\n')[0]).toBe('Nod: no state — no .nod/state.json in D:\\x\\other or above')
})

test('/nod migrate runs core migrate then opens the pane', async ($, on) => {
  const files: Record<string, string> = { [LEGACY_STATE]: '{}' }
  const calls = seat(on, {
    files,
    mtime: 1,
    run: argv => {
      if (argv.at(-1) !== 'migrate') return { exitCode: 0 }
      files[STATE] = JSON.stringify(STATE_FULL)

      return { exitCode: 0, stdout: 'moved to ' + DIR + '\n' }
    },
  })
  await startSession(calls, $)
  const opened = calls.opens.length
  const text = (await nodCommand($, 'migrate')).text ?? ''
  const migrate = calls.runs.findIndex(a => a.at(-1) === 'migrate')
  expect(calls.runs[migrate]?.slice(-3)).toEqual(['--root', ROOT, 'migrate'])
  expect(text.split('\n')).toEqual(['state migrated: ' + DIR + '; pane opened', 'moved to ' + DIR])
  expect(calls.opens.length).toBe(opened + 1)
  // After the migration the start tail reads the new state: nod status, then the snapshot in the pane.
  expect(calls.runs.slice(migrate + 1).some(a => a.at(-1) === 'status')).toBe(true)
  const ui = await mountPane($, 'desktop')
  expect(await ui.find({ key: 'legacy' })).toBeUndefined()
  expect((await ui.find({ key: 'zone:waiting:title' }))?.text).toBe('Waiting for you · 3')
})

test('/nod migrate on success shows the core warnings from stderr after stdout', async ($, on) => {
  const files: Record<string, string> = { [LEGACY_STATE]: '{}' }
  const warnings = 'warning: adapter "custom" is unknown, set to "default"\n\nwarning: harness.toml line 4 still names the old tool\n'
  const calls = seat(on, {
    files,
    mtime: 1,
    run: argv => {
      if (argv.at(-1) !== 'migrate') return { exitCode: 0 }
      files[STATE] = JSON.stringify(STATE_FULL)

      return { exitCode: 0, stdout: 'moved to ' + DIR + '\n', stderr: warnings }
    },
  })
  await startSession(calls, $)
  const text = (await nodCommand($, 'migrate')).text ?? ''
  expect(text.split('\n')).toEqual([
    'state migrated: ' + DIR + '; pane opened',
    'moved to ' + DIR,
    'warning: adapter "custom" is unknown, set to "default"',
    'warning: harness.toml line 4 still names the old tool',
  ])
})

for (const [code, stderr, reason] of [
  [2, 'error: .nod already exists\n', '.nod already exists'],
  [3, 'error: branch main is protected\n', 'branch main is protected'],
] as const) {
  test(`/nod migrate refused with code ${code} — "nod migrate failed: <the core's message>", no pane`, async ($, on) => {
    const calls = seat(on, { files: { [LEGACY_STATE]: '{}' }, run: argv => (argv.at(-1) === 'migrate' ? { exitCode: code, stderr } : {}) })
    await startSession(calls, $)
    const opened = calls.opens.length
    expect((await nodCommand($, 'migrate')).text).toBe('nod migrate failed: ' + reason)
    expect(calls.opens.length).toBe(opened)
  })
}

test('/nod doctor while the core probe runs — "still being checked", the core is not called', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' }, probeHang: true })
  await startSession(calls, $)
  expect((await nodCommand($, 'doctor')).text).toBe(EN.subChecking)
  expect(calls.runs.some(a => a.includes('doctor'))).toBe(false)
})

test('/nod doctor prints the core output, code 1 is not an error', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' }, run: argv => argv.includes('doctor') ? { exitCode: 1, stdout: 'need  have\npython  no' } : { exitCode: 0 } })
  await startSession(calls, $)
  expect((await nodCommand($, 'doctor')).text).toBe('need  have\npython  no')
  expect(calls.runs.find(a => a.includes('doctor'))!.slice(-3)).toEqual(['--root', DIR, 'doctor'])
})

test('/nod install without a state — "no state", the core is not called', async ($, on) => {
  const calls = seat(on, { files: {} })
  await startSession(calls, $, 'D:\\x\\other')
  expect((await nodCommand($, 'install')).text).toContain('no state')
  expect(calls.runs.some(a => a.includes('install'))).toBe(false)
})

test('/nod install: a core error — "nod install failed: …" without the error prefix', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' }, run: argv => argv.includes('install') ? { exitCode: 2, stderr: 'error: schtasks returned code 1' } : { exitCode: 0 } })
  await startSession(calls, $)
  expect((await nodCommand($, 'install')).text).toBe('nod install failed: schtasks returned code 1')
})

test('/nod nonsense — the list of subcommands', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: '{}' } })
  await startSession(calls, $)
  expect((await nodCommand($, 'nonsense')).text).toBe('unknown subcommand: /nod, /nod init, /nod migrate, /nod doctor, /nod install')
})
