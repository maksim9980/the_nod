import type { EngineInterface } from 'claude-code'

import { withCore } from './core-lock'
import { stateFile } from './find'
import { runNod } from './nod'
import type { Cell, PaneState } from './state'
import { parseSnapshot } from './snapshot'
import { noteLang, texts } from './texts/index'
import type { Snapshot } from './snapshot'

type Refresher = Pick<EngineInterface, 'fs' | 'process' | 'plugin' | 'ui' | 'clock'>

/** How to write atoms: straight into the cell by default; the click path gives a bounded write (no throw, no hang). */
export type Writer = <T>(cell: Cell<T>, value: T, label: string) => Promise<void>

const direct: Writer = (cell, value) => cell.write(value)

const describe = (err: unknown): string => (err instanceof Error ? err.message : String(err))

async function mtimeOf($: Refresher, path: string): Promise<number | null> {
  try {
    return (await $.fs.stat(path)).mtimeMs
  } catch {
    return null
  }
}

/**
 * Reads and parses the file; puts a new snapshot into the atom and returns it, otherwise null.
 * The cell reads go together with stat; loadError and lastMtime are written only when they change.
 * A new snapshot also sets the language of the texts (its `lang` field).
 */
async function readFile(
  $: Refresher, st: PaneState, path: string, force: boolean, w: Writer,
): Promise<Snapshot | null> {
  const [mtimeMs, lastMtime, loadError] = await Promise.all([mtimeOf($, path), st.lastMtime.read(), st.loadError.read()])
  if (mtimeMs === null) {
    await w(st.loadError, path + ': ' + texts().missingHint, 'loadError')

    return null
  }
  if (!force && mtimeMs === lastMtime) return null
  const parsed = parseSnapshot(await $.fs.read(path))
  if ('error' in parsed) {
    await w(st.loadError, path + ': ' + parsed.error, 'loadError')

    return null
  }
  noteLang(parsed.snapshot)
  await w(st.snapshot, parsed.snapshot, 'snapshot')
  await Promise.all([
    loadError === null ? undefined : w(st.loadError, null, 'loadError'),
    mtimeMs === lastMtime ? undefined : w(st.lastMtime, mtimeMs, 'lastMtime'),
  ])

  return parsed.snapshot
}
// A foreign since.from that has been re-anchored once: with a failing `nod status` the file stays foreign,
// and a new run on every tick would be a loop. Cleared when the file carries its own point again.
let reanchoredFrom: string | null = null

/**
 * The core rebuilds state.json after each of its writes, counting from the host's last visit, that is from the
 * start of this session, and the "While you were away" zone collapses. Bring the previous point back.
 */
async function keepSince(
  $: Refresher, st: PaneState, snapshot: Snapshot, sinceFrom: string | null, mayReanchor: boolean,
): Promise<void> {
  if (sinceFrom === null || sinceFrom === '') return
  if (snapshot.since.from === sinceFrom) {
    reanchoredFrom = null

    return
  }
  if (!mayReanchor || snapshot.since.from === reanchoredFrom) return
  const prefix = await st.nodPrefix.read()
  if (prefix === null || prefix === 'unknown') return
  reanchoredFrom = snapshot.since.from
  await refreshFromCore($, st, { sync: false })
}

/**
 * Rereads state.json if the mtime changed (or with force). Does not throw: an error goes to loadError.
 * `reanchor: false` — a call from firstLoad/refreshFromCore, which set the starting point themselves.
 */
export async function refresh(
  $: Refresher, st: PaneState, opts: { force?: boolean; reanchor?: boolean; write?: Writer } = {},
): Promise<void> {
  const w = opts.write ?? direct
  let path: string | null = null
  try {
    const [dir, sinceFrom] = await Promise.all([st.stateDir.read(), st.sinceFrom.read()])
    if (dir === null) return
    path = stateFile(dir)
    const snapshot = await readFile($, st, path, opts.force === true, w)
    if (snapshot !== null) await keepSince($, st, snapshot, sinceFrom, opts.reanchor !== false)
  } catch (err) {
    try {
      await w(st.loadError, (path === null ? '' : path + ': ') + describe(err), 'loadError')
    } catch {
      // nowhere to write — the timer must not fail
    }
  }
}

/** First read: `nod status` (pull, state.json rebuild, visit mark), then the snapshot and the "since last time" point. */
export async function firstLoad($: Refresher, st: PaneState): Promise<void> {
  try {
    const dir = await st.stateDir.read()
    if (dir === null) return
    const prefix = await st.nodPrefix.read()
    const ran = prefix !== null && prefix !== 'unknown' ? await withCore($, () => runNod($, prefix, dir, ['status'])) : null
    await refresh($, st, { force: true, reanchor: false })
    if (ran !== null && !ran.ok) await st.loadError.write(texts().nodStatusPrefix + ran.message)
    const snapshot = await st.snapshot.read()
    if (snapshot !== null) await st.sinceFrom.write(snapshot.since.from)
  } catch (err) {
    try {
      await st.loadError.write(describe(err))
    } catch {
      // nowhere to write
    }
  }
}

/** Asks the core to rebuild the snapshot (`nod status --peek`, under the core-lock slot), then rereads the file. Does not throw. */
export async function refreshFromCore($: Refresher, st: PaneState, opts: { sync: boolean }): Promise<void> {
  let failure: string | null = null
  try {
    const [dir, prefix, sinceFrom] = await Promise.all([st.stateDir.read(), st.nodPrefix.read(), st.sinceFrom.read()])
    if (dir !== null && prefix !== null && prefix !== 'unknown') {
      const ran = await withCore($, () => runNod($, prefix, dir, [
        'status',
        '--peek',
        ...(opts.sync ? [] : ['--no-sync']),
        ...(sinceFrom === null || sinceFrom === '' ? [] : ['--since', sinceFrom]),
      ]))
      if (!ran.ok) failure = texts().nodStatusPrefix + ran.message
    }
  } catch (err) {
    failure = describe(err)
  }
  await refresh($, st, { force: true, reanchor: false })
  if (failure === null) return
  try {
    await st.loadError.write(failure)
  } catch {
    // nowhere to write
  }
}
