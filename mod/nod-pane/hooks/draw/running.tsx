import type { RenderElement } from 'claude-code'

import type { Actions } from '../actions'
import type { Running, Snapshot } from '../snapshot'
import type { Texts } from '../texts/index'
import type { Ui } from './ui'

export type RunningModel = { items: Running[]; lock: Snapshot['lock']; host: string; nowMs: number }

/** Body of the "In a run" zone: the lock line of another machine, then a card per run. Read only. */
export function drawRunning(ui: Ui, t: Texts, m: RunningModel, _a: Actions, width: number): RenderElement {
  const { Box, Text } = ui
  const foreign = m.lock !== null && m.lock.host !== m.host ? m.lock : null

  return (
    <Box key="running:body" flexDirection="column" width={width}>
      {foreign === null ? null : (
        <Box key="lock"><Text color="warning" wrap="wrap">{t.lockLine(foreign.host, foreign.at)}</Text></Box>
      )}
      {m.items.length === 0 ? (
        <Box key="running:empty"><Text dimColor>{t.emptyRunning}</Text></Box>
      ) : m.items.map(r => (
        <Box key={'run:' + r.card} borderStyle="round" borderDimColor flexDirection="column">
          <Box key={`run:${r.card}:title`}><Text weight="semibold" wrap="wrap">{r.card_title}</Text></Box>
          <Box key={`run:${r.card}:step`}>
            <Text wrap="wrap">{r.step === null ? t.noStep : `${t.step} ${r.step}: ${r.step_title ?? ''}`}</Text>
          </Box>
          <Box key={`run:${r.card}:contracts`}>
            <Text wrap="wrap">
              <Text mono>{t.contracts} {r.contracts_done}/{r.contracts_total}</Text>
              {r.started === null ? '' : ` · ${t.runningFor} ${t.formatAge(r.started, m.nowMs)}`}
            </Text>
          </Box>
        </Box>
      ))}
    </Box>
  )
}
