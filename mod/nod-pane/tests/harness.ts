// Shared test harness: `seat` answers for the world under the mod, `startSession` starts a session,
// `mountPane` draws the pane.
//   const calls = seat(on, { files: { [STATE]: '{}' } })   // before the first call of $
//   await startSession(calls, $, cwd)                      // session.start + settle of the clock
// `startSession` waits for `calls.clock.settle()`: the mod's session.start hook does the search and ui.open
// without waiting, and without settle a test would look at an unfinished chain.
import { mock } from 'claude-code/testing'
import type { On, PaneOpenArgs, ProcessRunResult } from 'claude-code'
import { DIR, PANE_PROPS, ROOT, NOD, WRITE_KEYS } from './fixtures'

const noPython = (argv: readonly string[]): { exitCode: number } | undefined =>
  argv.at(-1) === '--help' && argv.at(-2)?.endsWith('__main__.py') ? { exitCode: 127 } : undefined

export type World = {
  files: Record<string, string>
  mtime?: number
  run?: (argv: readonly string[]) => Partial<ProcessRunResult> | { deny: string } | Promise<Partial<ProcessRunResult> | { deny: string }>
  /** true — Python is in PATH, and the core is taken by `python -P`; by default python and py do not answer, `nod` is taken. */
  pythonCore?: boolean
  placed?: boolean
  placeReason?: string
  openDeny?: string
  submitDeny?: string
  submitDelay?: number
  readDeny?: string
  registerDeny?: string
  /** How many first `command.register` calls refuse with `registerDeny`; without the field — all. */
  registerDenyTimes?: number
  /** How many first `command.list` calls give a list without the registered names. */
  listHide?: number
  /** `command.list` answers with something other than an array (`{ value: null }`). */
  listNull?: boolean
  /** How many first `command.register` calls never answer (hang). */
  registerHangTimes?: number
  /** The core probe (`… --help`) never answers: the prefix stays `'unknown'`. */
  probeHang?: boolean
  now?: number
}

export type Calls = {
  opens: PaneOpenArgs[]
  runs: (readonly string[])[]
  cwds: (string | undefined)[]
  reads: string[]
  stats: string[]
  prompts: string[]
  statuses: string[]
  /** Debug log lines (`$.ui.log(text, { to: 'debug' })`). */
  logs: string[]
  /** Visible transcript lines (`$.ui.log(text)` without `to: 'debug'`). */
  transcript: string[]
  toasts: string[]
  /** Command names from `$.command.register`, in order. */
  registers: string[]
  /** How many times the mod asked `$.command.list()`. */
  lists: number
  invalidates: string[]
  /** Shared journal in order: `status:<text>` and `run:<argv joined by spaces>` — for "what came first" checks. */
  events: string[]
  clock: ReturnType<typeof mock.clock>
}

// On Windows the kit turns fs paths into `D:\...` before the world hook: look a file up without the drive and with "/".
const norm = (path: string): string => path.replace(/^[A-Za-z]:/, '').replace(/\\/g, '/')

export const seat = (on: On, world: World): Calls => {
  const clock = mock.clock(on, { now: world.now ?? Date.parse('2026-10-20T10:00:00') })
  const calls: Calls = { opens: [], runs: [], cwds: [], reads: [], stats: [], prompts: [], statuses: [], logs: [], transcript: [], toasts: [], registers: [], lists: 0, invalidates: [], events: [], clock }

  const files = (path: string): string | undefined =>
    Object.entries(world.files).find(([key]) => norm(key) === norm(path))?.[1]
  let cwd = ROOT
  on('session.start', (_: unknown, e: { cwd?: string }) => {
    cwd = e.cwd ?? cwd

    return { cwd }
  })
  // The engine registry: a successful registration puts the name, `command.list` gives a built-in command and the registry.
  const registry = new Set<string>()
  on('command.register', (_: unknown, e: { name: string }) => {
    calls.registers.push(e.name)
    if (calls.registers.length <= (world.registerHangTimes ?? 0)) return new Promise<never>(() => undefined)
    const denied = world.registerDeny !== undefined
      && (world.registerDenyTimes === undefined || calls.registers.length <= world.registerDenyTimes)
    if (denied) return { deny: world.registerDeny! }
    registry.add(e.name)

    return { value: { command: e.name } }
  })
  on('command.list', () => {
    calls.lists += 1
    if (world.listNull === true) return { value: null }
    const own = calls.lists <= (world.listHide ?? 0) ? [] : [...registry]

    return { value: [
      { name: 'help', description: 'Help', source: 'builtin' },
      ...own.map(name => ({ name, description: 'Open the Nod pane', source: 'plugin', plugin: 'nod' })),
    ] }
  })
  // Bottom of turn.complete: the turn's answer as is — the mod must return it through next.
  on('turn.complete', (_: unknown, e: { answer: string }) => ({ text: e.answer }))
  on('session.cwd', () => ({ value: cwd }))
  on('fs.exists', (_: unknown, e: { path: string }) => ({ value: files(e.path) !== undefined }))
  on('fs.stat', (_: unknown, e: { path: string }) => {
    calls.stats.push(e.path)

    return files(e.path) !== undefined
      ? { value: { kind: 'file', size: files(e.path)!.length, mtimeMs: world.mtime ?? 1, isLink: false } }
      : { deny: 'ENOENT' }
  })
  on('fs.read', (_: unknown, e: { path: string }) => {
    calls.reads.push(e.path)
    if (world.readDeny !== undefined) return { deny: world.readDeny }

    return { value: files(e.path) }
  })
  on('process.run', async (_: unknown, e: { argv: readonly string[]; init?: { cwd?: string } }) => {
    calls.runs.push(e.argv)
    calls.cwds.push(e.init?.cwd)
    calls.events.push('run:' + e.argv.join(' '))
    if (world.probeHang === true && e.argv.at(-1) === '--help') return new Promise<never>(() => undefined)

    const answer = (world.pythonCore === true ? undefined : noPython(e.argv)) ?? (await world.run?.(e.argv))
    if (answer !== undefined && 'deny' in answer) return { deny: answer.deny }

    return {
      value: {
        exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false,
        ...answer,
      },
    }
  })
  on('ui.open', (_: unknown, e: PaneOpenArgs) => {
    calls.opens.push(e)
    if (world.openDeny !== undefined) return { deny: world.openDeny }

    return { value: world.placed === false
      ? { isPlaced: false, reason: world.placeReason ?? 'the terminal is narrower than 144 columns' }
      : { isPlaced: true } }
  })
  on('prompt.submit', async (_: unknown, e: { text: string }) => {
    if (world.submitDeny !== undefined) return { drop: world.submitDeny }
    if (world.submitDelay !== undefined) await clock.sleep(world.submitDelay)
    calls.prompts.push(e.text)

    return { text: e.text }
  })
  on('ui.log', (_: unknown, e: { text: string; to?: string }) => {
    if (e.to === 'debug') calls.logs.push(e.text)
    else calls.transcript.push(e.text)

    return { value: undefined }
  })
  on('ui.toast', (_: unknown, e: { text: string }) => {
    calls.toasts.push(e.text)
    calls.events.push('toast:' + e.text)

    return { value: undefined }
  })
  // Down through next: the kit itself redraws the mounted pane (the click state lives in the module,
  // a redraw comes only through invalidate).
  on('ui.invalidate', (async (_: unknown, e: { event: string }, next: (e: unknown) => Promise<unknown>) => {
    calls.invalidates.push(e.event)

    return next(e)
  }) as never)
  on('ui.status', (_: unknown, e: { text: string }) => {
    calls.statuses.push(e.text)
    calls.events.push('status:' + String(e.text))

    return { value: undefined }
  })

  return calls
}

type Engine = Parameters<Parameters<typeof import('claude-code/testing').test>[1]>[0]

export const startSession = async (calls: Calls, $: Engine, cwd: string = ROOT) => {
  await $.session.start({ cwd, surface: 'desktop', isInteractive: true })
  await calls.clock.settle()
}

export const mountPane = ($: Engine, surface: 'desktop' | 'terminal', props: object = PANE_PROPS) =>
  $.ui.mount({ plugin: 'nod', surface, component: 'Pane', requestId: 'nod', props } as never)

export const runNod = (args: string[]) => [...NOD, '--root', DIR, ...args]

export type Mounted = Awaited<ReturnType<typeof mountPane>>

/** Write buttons on screen: a Button with a key from WRITE_KEYS. */
export const writeButtons = async (ui: Mounted) =>
  (await ui.findAll({ type: 'Button' })).filter(b => WRITE_KEYS.some(k => String(b.key ?? '').startsWith(k)))
