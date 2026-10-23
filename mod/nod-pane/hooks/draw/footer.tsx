import type { RenderElement } from 'claude-code'

import type { Actions } from '../actions'
import type { LastAction } from '../state'
import type { Texts } from '../texts/index'
import type { Ui } from './ui'

/** The "last action" line: an error in error, a skip in warning, the rest dimmed. */
function drawLastAction(ui: Ui, t: Texts, last: LastAction): RenderElement {
  const { Box, Text } = ui
  const color = last.result === 'error' ? 'error' : last.result === 'ignored' ? 'warning' : undefined

  return (
    <Box key="last-action">
      <Text color={color} dimColor={color === undefined} wrap="wrap">{t.lastActionLine(last)}</Text>
    </Box>
  )
}

/** The "Goes to the chat" draft and two buttons; an empty draft — null. */
function drawDraft(ui: Ui, t: Texts, draft: string, a: Actions, width: number): RenderElement | null {
  const { Box, Text, Button } = ui
  if (draft === '') return null

  return (
    <Box key="footer" borderStyle="round" borderDimColor flexDirection="column" width={width}>
      <Box key="footer:title">
        <Text size="caption" mono dimColor>{t.toChat}</Text>
      </Box>
      <Box key="draft">
        <Text wrap="wrap">{draft}</Text>
      </Box>
      <Box key="footer:row" flexDirection="row" gap={1}>
        <Button key="send" variant="primary" hotkey="s" label={t.send} onPress={() => a.send()} />
        <Button key="clear" variant="secondary" label={t.clear} onPress={() => a.clearDraft()} />
      </Box>
    </Box>
  )
}

/** The footer: the draft (if any) and the last action line (if there was one); neither — null. */
export function drawFooter(
  ui: Ui, t: Texts, draft: string, last: LastAction | null, a: Actions, width: number,
): RenderElement | null {
  const { Box } = ui
  const body = drawDraft(ui, t, draft, a, width)
  if (body === null && last === null) return null

  return (
    <Box key="bottom" flexDirection="column" width={width}>
      {body}
      {last === null ? null : drawLastAction(ui, t, last)}
    </Box>
  )
}
