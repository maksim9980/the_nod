import type { RenderElement } from 'claude-code'

import type { Actions } from '../actions'
import { sepOf } from '../find'
import { proposed } from '../snapshot'
import type { Snapshot } from '../snapshot'
import type { LastAction, Progress, WriteError } from '../state'
import { textsFor } from '../texts/index'
import type { Lang, Texts } from '../texts/index'
import type { Ui } from './ui'
import { drawBacklog, drawNextStep } from './backlog'
import { drawFooter } from './footer'
import { drawReview } from './review'
import { drawRunning } from './running'
import { drawSince } from './since'
import { drawWaiting } from './waiting'

export type PaneModel = {
  snapshot: Snapshot | null
  loadError: string | null
  stateDir: string | null
  nowMs: number
  pending: string | null
  progress: Progress | null
  writeError: WriteError | null
  draft: string
  expanded: string[]
  freeFor: string | null
  lastAction: LastAction | null
  /** Which time this instance draws the pane and when (engine clock): shows whether the frame is fresh. */
  renders: number
  /** Whether the pane holds the keyboard (`e.props.isFocused`): without it the first click goes to the focus. */
  focused: boolean
  /** The line "the mod is loaded twice…" or null (owner.ts). */
  doubleLoad: string | null
  nodMissing: boolean
  /** No `.nod`, but an older version's state folder is found: the pane suggests `/nod migrate`. */
  legacy: boolean
  /** Language of the texts: the snapshot's `lang`, or the last snapshot's one before a snapshot is read. */
  lang: Lang
}

/** Writes are allowed only on a fresh state and with nod found. */
export const canWrite = (m: PaneModel): boolean => m.snapshot?.fresh === true && !m.nodMissing

/** Name of the project folder: the last segment of the parent of `.nod`. */
function projectName(stateDir: string): string {
  const parts = stateDir.split(sepOf(stateDir)).filter(p => p !== '')

  return parts.length >= 2 ? (parts[parts.length - 2] ?? '') : (parts[0] ?? '')
}

type Zone = { id: string; name: string; count: number | string; accent: boolean; empty: string | null }

function zones(s: Snapshot, t: Texts): Zone[] {
  const r = s.review

  return [
    // With an empty queue and a non-empty backlog the "Next step" card says "No decisions".
    {
      id: 'waiting', name: t.zoneWaiting, count: s.waiting.length, accent: s.waiting.length > 0,
      empty: s.waiting.length === 0 && s.backlog.total === 0 ? t.emptyWaiting : null,
    },
    { id: 'running', name: t.zoneRunning, count: s.running.length, accent: false, empty: null },
    {
      id: 'since', name: t.zoneSince, count: t.sinceCount(s.since.from), accent: false, empty: null,
    },
    { id: 'backlog', name: t.zoneBacklog, count: s.backlog.total, accent: false, empty: null },
    // The zone is drawn without a review too: the empty line suggests the command.
    {
      id: 'review', name: t.zoneReview, count: r ? r.week : '—',
      accent: r !== null && r !== undefined && proposed(r).length > 0, empty: null,
    },
  ]
}

function drawZone(ui: Ui, t: Texts, z: Zone, body: RenderElement | null): RenderElement {
  const { Box, Text } = ui
  const key = 'zone:' + z.id

  return (
    <Box key={key} flexDirection="column">
      <Box key={key + ':title'}>
        <Text size="caption" mono color={z.accent ? 'success' : undefined} dimColor={!z.accent}>
          {t.zoneTitle(z.name, z.count)}
        </Text>
      </Box>
      {body}
      {z.empty === null ? null : (
        <Box key={key + ':empty'}>
          <Text dimColor>{z.empty}</Text>
        </Box>
      )}
    </Box>
  )
}

/** Body of a zone by its id. */
function zoneBody(ui: Ui, t: Texts, id: string, s: Snapshot, m: PaneModel, a: Actions, width: number): RenderElement | null {
  if (m.stateDir === null) return null
  if (id === 'running') return drawRunning(ui, t, { items: s.running, lock: s.lock, host: s.host, nowMs: m.nowMs }, a, width)
  if (id === 'since') return drawSince(ui, t, s.since, a, width)
  if (id === 'backlog') return drawBacklog(ui, t, s.backlog, m.stateDir, s.waiting.length > 0, a, width)
  if (id === 'review') return drawReview(ui, t, s.review, m.stateDir, a, width)
  if (id !== 'waiting') return null
  if (s.waiting.length === 0) return drawNextStep(ui, t, s.backlog, m.stateDir, a, width)

  return drawWaiting(ui, {
    items: s.waiting,
    canWrite: canWrite(m),
    pending: m.pending,
    progress: m.progress,
    writeError: m.writeError,
    expanded: m.expanded,
    freeFor: m.freeFor,
    stateDir: m.stateDir,
    t,
  }, a, width)
}

function drawNotices(ui: Ui, t: Texts, m: PaneModel, a: Actions): RenderElement[] {
  const { Box, Text, Button } = ui
  const out: RenderElement[] = []
  if (m.doubleLoad !== null) {
    out.push(
      <Box key="double-load">
        <Text color="warning" wrap="wrap">{m.doubleLoad}</Text>
      </Box>,
    )
  }
  if (m.snapshot !== null && !m.snapshot.fresh) {
    out.push(
      <Box key="stale">
        <Text color="warning" wrap="wrap">{t.staleLine(m.snapshot.stale_since ?? m.snapshot.generated_at)}</Text>
      </Box>,
    )
  }
  if (m.nodMissing) {
    out.push(
      <Box key="nod-missing">
        <Text color="warning" wrap="wrap">{t.nodMissing}</Text>
      </Box>,
    )
  }
  if (m.loadError !== null) {
    out.push(
      <Box key="load-error">
        <Text color="error" wrap="wrap">{m.loadError}</Text>
      </Box>,
      <Button key="refresh" label={t.refresh} variant="secondary" onPress={() => a.refresh()} />,
    )
  }

  return out
}

export function drawPane(ui: Ui, m: PaneModel, a: Actions, width: number): RenderElement {
  const { Box, Text } = ui
  const t = textsFor(m.lang)
  if (m.stateDir === null) {
    return m.legacy ? (
      <Box key="legacy">
        <Text color="warning" wrap="wrap">{t.legacyFound}</Text>
      </Box>
    ) : (
      <Box key="loading">
        <Text dimColor>{t.loading}</Text>
      </Box>
    )
  }
  const s = m.snapshot
  const head = s === null ? [] : [
    <Box key="header">
      <Text dimColor wrap="truncate-end">
        {t.headerLine(projectName(m.stateDir), s.host, t.formatAge(s.generated_at, m.nowMs)) + t.renderedTail(m.nowMs, m.renders)}
      </Text>
    </Box>,
    ...(m.focused ? [] : [<Box key="focus-hint"><Text dimColor wrap="wrap">{t.focusHint}</Text></Box>]),
    ...zones(s, t).map(z => drawZone(ui, t, z, zoneBody(ui, t, z.id, s, m, a, width))),
  ]
  const waiting = s === null && m.loadError === null
    ? [<Box key="loading"><Text dimColor>{t.loading}</Text></Box>]
    : []

  return (
    <Box key="pane" flexDirection="column" gap={1} width={width}>
      {drawNotices(ui, t, m, a)}
      {waiting}
      {head}
      {drawFooter(ui, t, m.draft, m.lastAction, a, width)}
    </Box>
  )
}
