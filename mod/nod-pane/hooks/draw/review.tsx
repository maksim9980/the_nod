import type { RenderElement } from 'claude-code'

import type { Actions } from '../actions'
import { proposed } from '../snapshot'
import type { Review, ReviewSuggestion } from '../snapshot'
import type { Texts } from '../texts/index'
import type { Ui } from './ui'

export const REVIEW_SHOWN = 5

/** A suggestion line; an applied one is dimmed whole, the status is a dim tail. */
function suggestionRow(ui: Ui, t: Texts, s: ReviewSuggestion): RenderElement {
  const { Box, Text } = ui

  return (
    <Box key={'rv:' + s.n}>
      <Text wrap="wrap" dimColor={s.status === 'applied'}>
        {t.suggestionLine(s)}
        <Text dimColor> · {t.suggestionStatus(s.status)}</Text>
      </Text>
    </Box>
  )
}

/** List of suggestions: a green frame only while there are proposed ones — the owner's move. */
function suggestionList(ui: Ui, t: Texts, r: Review, waiting: boolean): RenderElement {
  const { Box, Text } = ui
  const rows = r.suggestions.length === 0
    ? [<Box key="review:none"><Text dimColor>{t.noSuggestions}</Text></Box>]
    : r.suggestions.slice(0, REVIEW_SHOWN).map(s => suggestionRow(ui, t, s))
  const tail = r.suggestions.length > REVIEW_SHOWN
    ? <Box key="review:more"><Text dimColor>{t.more(r.suggestions.length - REVIEW_SHOWN)}</Text></Box>
    : null

  return waiting ? (
    <Box key="review:list" flexDirection="column" borderStyle="round" borderColor="success">{rows}{tail}</Box>
  ) : (
    <Box key="review:list" flexDirection="column">{rows}{tail}</Box>
  )
}

/** Body of the "Weekly review" zone: period, counters, suggestions and the prompt button. Writes nothing to $.state. */
export function drawReview(
  ui: Ui, t: Texts, r: Review | null | undefined, stateDir: string, a: Actions, width: number,
): RenderElement {
  const { Box, Text, Button } = ui
  if (r === null || r === undefined) {
    return <Box key="review:body" width={width}><Box key="review:empty"><Text dimColor>{t.emptyReview}</Text></Box></Box>
  }
  const waiting = proposed(r).length > 0

  return (
    <Box key="review:body" flexDirection="column" width={width}>
      <Box key="review:period"><Text dimColor>{t.reviewPeriod(r)}</Text></Box>
      <Box key="review:counters"><Text mono wrap="wrap">{t.reviewLine(r)}</Text></Box>
      {suggestionList(ui, t, r, waiting)}
      {waiting ? (
        <Button key="review:apply" variant="primary" label={t.applySuggestions} onPress={() => a.draft(t.promptApply(r, stateDir))} />
      ) : null}
    </Box>
  )
}
