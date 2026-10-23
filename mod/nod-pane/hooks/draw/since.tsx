import type { RenderElement } from 'claude-code'

import type { Actions } from '../actions'
import type { Since } from '../snapshot'
import type { Texts } from '../texts/index'
import type { Ui } from './ui'

export const SINCE_SHOWN = 10

const isQuiet = (s: Since): boolean =>
  s.runs === 0 && s.steps_done === 0 && s.accepted === 0 && s.tokens === 0 && s.cards_done.length === 0

/** Body of the "While you were away" zone: counters and the first SINCE_SHOWN closed cards. Read only. */
export function drawSince(ui: Ui, t: Texts, s: Since, _a: Actions, width: number): RenderElement {
  const { Box, Text } = ui
  if (isQuiet(s)) {
    return <Box key="since:body" width={width}><Box key="since:empty"><Text dimColor>{t.emptySince}</Text></Box></Box>
  }

  return (
    <Box key="since:body" flexDirection="column" width={width}>
      <Box key="since:counters"><Text mono wrap="wrap">{t.countersLine(s)}</Text></Box>
      {s.cards_done.slice(0, SINCE_SHOWN).map(c => (
        <Box key={'done:' + c.id}>
          <Text wrap="truncate-end">
            {c.title}
            <Text dimColor> · {t.formatDate(c.closed_at)}</Text>
          </Text>
        </Box>
      ))}
      {s.cards_done.length > SINCE_SHOWN ? (
        <Box key="since:more"><Text dimColor>{t.more(s.cards_done.length - SINCE_SHOWN)}</Text></Box>
      ) : null}
    </Box>
  )
}
