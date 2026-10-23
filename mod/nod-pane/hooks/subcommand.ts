// Subcommands of /nod: init, migrate, doctor, install call the core directly and print its output.
// init and migrate work without a state folder: the core creates `.nod` (init) or moves the older version's folder
// to it (migrate) in the root of the repository's main worktree (outside a repository — in cwd), then the start
// tail (attach) opens the pane.
import type { EngineInterface } from 'claude-code'

import { findLegacyDir, mainWorktree } from './find'
import { local } from './local'
import { resolveNod, runNod } from './nod'
import { tryRead } from './state'
import type { PaneState } from './state'
import { texts } from './texts/index'

export type Sub = 'init' | 'migrate' | 'doctor' | 'install'

export const SUBS: readonly Sub[] = ['init', 'migrate', 'doctor', 'install']

export type SubDeps = { attach: (cwd: string) => Promise<string | null> }

type Finder = Pick<EngineInterface, 'fs' | 'process' | 'plugin'>

/** Subcommand from the /nod argument; not a subcommand — null. */
export const subOf = (args: string): Sub | null => SUBS.find(s => s === args) ?? null

/** Answer when there is no `.nod`: the older version's folder suggests `/nod migrate`, otherwise "no state". */
export async function noStateAnswer($: Finder, cwd: string): Promise<string> {
  const legacy = await findLegacyDir($, cwd)
  const t = texts()

  return legacy === null ? t.noState(cwd) : t.legacyFound
}

/**
 * /nod init and /nod migrate: find the core, run it in the root of the repository's main worktree (outside a
 * repository — in cwd), then find `.nod` and open the pane. The answer comes after the pane read the snapshot:
 * in the snapshot's language. A successful migrate also shows its stderr lines after stdout: the core warns there
 * (an unknown adapter, lines with the old name in harness.toml).
 */
async function runInRoot($: EngineInterface, sub: 'init' | 'migrate', configured: string, deps: SubDeps): Promise<string> {
  const cwd = await $.session.cwd()
  const probe = await resolveNod($, configured)
  if (probe.prefix === null) {
    const t = texts()

    return t.subNoNod + '\n' + t.nodNotFound + probe.tried.map(line => '\n' + line).join('')
  }
  const target = (await mainWorktree($, cwd)) ?? cwd
  const ran = await runNod($, probe.prefix, target, [sub])
  if (!ran.ok) return texts().subFailed(sub, ran.message)
  const dir = await deps.attach(cwd)
  const t = texts()
  if (sub === 'init') return t.initDone(dir ?? target) + '\n' + ran.stdout.trim()
  const warnings = ran.stderr.split(/\r?\n/).map(line => line.trim()).filter(line => line !== '')

  return [t.migrateDone(dir ?? target), ran.stdout.trim(), ...warnings].filter(line => line !== '').join('\n')
}

/** /nod doctor and /nod install: folder and core from $.state, on silence — the start copies; exit code 1 is not an error. */
async function runOnState($: EngineInterface, st: PaneState, sub: 'doctor' | 'install'): Promise<string> {
  const [dirRead, prefixRead] = await Promise.all([tryRead($, st.stateDir), tryRead($, st.nodPrefix)])
  const dir = (dirRead.ok ? dirRead.value : null) ?? local.lastStateDir
  if (dir === null) return noStateAnswer($, await $.session.cwd())
  const prefix = prefixRead.ok ? prefixRead.value : local.lastNodPrefix
  if (prefix === 'unknown') return texts().subChecking
  if (prefix === null) return texts().subNoNod
  const ran = await runNod($, prefix, dir, [sub])
  const out = ran.stdout.trim()

  return out === '' && !ran.ok ? texts().subFailed(sub, ran.message) : out
}

export async function runSubcommand(
  $: EngineInterface,
  st: PaneState,
  sub: Sub,
  configured: string,
  deps: SubDeps,
): Promise<string> {
  return sub === 'init' || sub === 'migrate' ? runInRoot($, sub, configured, deps) : runOnState($, st, sub)
}

/** Answer of /nod with an argument: the subcommand's output or the list of subcommands. */
export async function replyTo(
  $: EngineInterface,
  st: PaneState,
  args: string,
  configured: string,
  deps: SubDeps,
): Promise<string> {
  const sub = subOf(args)

  return sub === null ? texts().subUnknown : runSubcommand($, st, sub, configured, deps)
}
