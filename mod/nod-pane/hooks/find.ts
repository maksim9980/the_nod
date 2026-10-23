import type { EngineInterface } from 'claude-code'

export const STATE_DIR = '.nod'
export const STATE_FILE = 'state.json'
/** State folder of an older version: found, it makes /nod and the pane suggest `/nod migrate`. */
export const LEGACY_DIR = '.sprintboot'

type Sep = '\\' | '/'

const SEPARATORS = /[\\/]/g
const TRAILING = /[\\/]+$/

/** Path separator: the first `\` or `/` met in the path. */
export const sepOf = (path: string): Sep => {
  const at = path.search(/[\\/]/)

  return at >= 0 && path[at] === '\\' ? '\\' : '/'
}

export const stateFile = (dir: string): string => dir + sepOf(dir) + STATE_FILE

type Finder = Pick<EngineInterface, 'fs' | 'process' | 'plugin'>

/** Climbs from `start` to the root; the first `<dir>/<folder>` holding `state.json`, or `null`. */
async function climb(
  $: Pick<EngineInterface, 'fs'>,
  start: string,
  sep: Sep,
  folder: string,
): Promise<string | null> {
  let dir = start.replace(SEPARATORS, sep).replace(TRAILING, '')
  for (;;) {
    const candidate = dir + sep + folder
    if (await $.fs.exists(candidate + sep + STATE_FILE)) return candidate
    const cut = dir.lastIndexOf(sep)
    if (cut < 0) return null
    dir = dir.slice(0, cut)
  }
}

/** Root of the repository's main worktree by `git worktree list`; not a repository or git silent — `null`. */
export async function mainWorktree(
  $: Pick<EngineInterface, 'process' | 'plugin'>,
  cwd: string,
): Promise<string | null> {
  try {
    const ran = await $.process.run(['git', '-C', cwd, 'worktree', 'list', '--porcelain'], { cwd: $.plugin.root })
    if (ran.exitCode !== 0) return null
    const first = ran.stdout.split(/\r?\n/)[0] ?? ''

    return first.startsWith('worktree ') ? first.slice('worktree '.length).trim() || null : null
  } catch {
    return null
  }
}

/** A state folder up from `cwd`, then up from the main worktree; with the separator of `cwd`. */
async function findFolder($: Finder, cwd: string, folder: string): Promise<string | null> {
  const sep = sepOf(cwd)
  const up = await climb($, cwd, sep, folder)
  if (up !== null) return up
  const main = await mainWorktree($, cwd)

  return main === null ? null : climb($, main, sep, folder)
}

/** Absolute path to `.nod` (with the separator of `cwd`) or `null`. */
export async function findStateDir($: Finder, cwd: string): Promise<string | null> {
  return findFolder($, cwd, STATE_DIR)
}

/** Absolute path to the state folder of an older version, or `null`: searched only when `.nod` is not found. */
export async function findLegacyDir($: Finder, cwd: string): Promise<string | null> {
  return findFolder($, cwd, LEGACY_DIR)
}
