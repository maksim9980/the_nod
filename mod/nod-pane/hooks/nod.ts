import type { EngineInterface } from 'claude-code'

import { timed } from './log'
import { sepOf } from './find'
import { ERROR_PREFIXES, texts } from './texts/index'

export const NOD_TIMEOUT_MS = 60000

const PROBE_TIMEOUT_MS = 15000

export type NodRun = {
  ok: boolean
  exitCode: number
  stdout: string
  stderr: string
  message: string
}

type ProcessOnly = Pick<EngineInterface, 'process' | 'plugin'>

/** runNod also times the run and writes it to the debug log. */
export type NodRunner = Pick<EngineInterface, 'process' | 'plugin' | 'ui'>

/** Outcome of the core search: the argv prefix (`null` — nobody answered) and a line per failed candidate. */
export type NodProbe = { prefix: readonly string[] | null; tried: readonly string[] }

/** Path to `the_nod/__main__.py` inside the plugin root, with the separator of the root. */
export const coreMain = (root: string): string => {
  const sep = sepOf(root)

  return root + sep + 'the_nod' + sep + '__main__.py'
}

/**
 * Candidates in order: your own command, `python -P`, `python3 -P`, `py -3 -P`, `nod` from PATH.
 * macOS and stock Ubuntu have `python3` only; the Windows launcher is `py`.
 */
export const candidates = (root: string, configured: string): readonly (readonly string[])[] => {
  const custom = configured.trim()

  return [
    ...(custom === '' ? [] : [custom.split(/\s+/)]),
    ['python', '-P', coreMain(root)],
    ['python3', '-P', coreMain(root)],
    ['py', '-3', '-P', coreMain(root)],
    ['nod'],
  ]
}

const firstLine = (stderr: string): string => stderr.split(/\r?\n/).map(l => l.trim()).find(l => l !== '') ?? ''

/** Tries the candidates in order with `<candidate> --help` and stops at the first one with exit code 0. */
export async function resolveNod($: ProcessOnly, configured: string): Promise<NodProbe> {
  const tried: string[] = []
  for (const prefix of candidates($.plugin.root, configured)) {
    const argv = [...prefix, '--help']
    try {
      const ran = await $.process.run(argv, { cwd: $.plugin.root, timeoutMs: PROBE_TIMEOUT_MS })
      if (ran.exitCode === 0) return { prefix, tried }
      const t = texts()
      tried.push(t.probeLine(argv, t.probeExit(ran.exitCode, firstLine(ran.stderr))))
    } catch {
      const t = texts()
      tried.push(t.probeLine(argv, t.probeNoStart))
    }
  }

  return { prefix: null, tried }
}

/** The first stderr line without the core's error prefix of either language. */
const failureMessage = (exitCode: number, stderr: string): string => {
  const first = stderr.split(/\r?\n/).find(line => line.trim() !== '')
  if (first === undefined) return texts().exitCodeLine(exitCode)
  const line = first.trim()
  const prefix = ERROR_PREFIXES.find(p => line.startsWith(p))

  return prefix === undefined ? line : line.slice(prefix.length)
}

/**
 * Runs `nod --root <stateDir> <args>`; a failed start does not throw but comes back in `message`; cwd is the
 * mod folder, not the project. The duration goes to the debug log as `nod <first two args> — <ms> ms, code <N>`.
 */
export async function runNod(
  $: NodRunner,
  prefix: readonly string[],
  stateDir: string,
  args: readonly string[],
  timeoutMs: number = NOD_TIMEOUT_MS,
): Promise<NodRun> {
  const argv = [...prefix, '--root', stateDir, ...args]
  try {
    const label = ['nod', ...args.slice(0, 2)].join(' ')
    const ran = await timed(
      $, label, () => $.process.run(argv, { cwd: $.plugin.root, timeoutMs }), r => texts().exitTail(r.exitCode),
    )
    const ok = ran.exitCode === 0

    return {
      ok,
      exitCode: ran.exitCode,
      stdout: ran.stdout,
      stderr: ran.stderr,
      message: ok ? '' : failureMessage(ran.exitCode, ran.stderr),
    }
  } catch {
    return { ok: false, exitCode: -1, stdout: '', stderr: '', message: texts().cannotStart(argv[0] ?? '') }
  }
}
