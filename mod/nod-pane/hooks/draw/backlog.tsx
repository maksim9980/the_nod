import type { RenderElement } from 'claude-code'

import type { Actions } from '../actions'
import type { Snapshot } from '../snapshot'
import type { Texts } from '../texts/index'
import type { Ui } from './ui'

export const BACKLOG_SHOWN = 5

type Backlog = Snapshot['backlog']

/** Row of prompt buttons: "Show the backlog" (if there is something to show) and "Name another pain". The tree keys never change. */
function promptRow(ui: Ui, t: Texts, stateDir: string, a: Actions, withShow: boolean): RenderElement {
  const { Box, Button } = ui

  return (
    <Box key="backlog:buttons" flexDirection="row" flexWrap="wrap" gap={1}>
      {withShow ? (
        <Button key="backlog:show" label={t.showBacklog} variant="secondary" onPress={() => a.draft(t.promptBacklog(stateDir))} />
      ) : null}
      <Button key="backlog:pain" label={t.ownPain} variant="secondary" onPress={() => a.draft(t.promptPain)} />
    </Box>
  )
}

/** Body of the "Backlog" zone: the top five lines, "N more" and, with `withButtons`, the prompt buttons. */
export function drawBacklog(
  ui: Ui, t: Texts, b: Backlog, stateDir: string, withButtons: boolean, a: Actions, width: number,
): RenderElement {
  const { Box, Text } = ui

  return (
    <Box key="backlog:body" flexDirection="column" width={width}>
      {b.total === 0 ? (
        <Box key="backlog:empty"><Text dimColor>{t.emptyBacklog}</Text></Box>
      ) : b.top.slice(0, BACKLOG_SHOWN).map((c, i) => (
        <Box key={'bl:' + c.id}>
          <Text wrap="truncate-end">
            {i + 1}. {c.title}
            <Text dimColor> · {c.status}{c.brief ? ' · ' + t.briefReady : ''}</Text>
          </Text>
        </Box>
      ))}
      {b.total > BACKLOG_SHOWN ? (
        <Box key="backlog:more"><Text dimColor>{t.more(b.total - BACKLOG_SHOWN)}</Text></Box>
      ) : null}
      {withButtons ? promptRow(ui, t, stateDir, a, b.total > 0) : null}
    </Box>
  )
}

/** The "Next step" card instead of decisions: take the top of the backlog or, with an empty backlog, sort out the pain. */
export function drawNextStep(ui: Ui, t: Texts, b: Backlog, stateDir: string, a: Actions, width: number): RenderElement {
  const { Box, Text, Button } = ui
  const first = b.top[0]
  if (b.total === 0 || first === undefined) {
    return (
      <Box key="next" flexDirection="column" borderStyle="round" borderColor="success" width={width}>
        <Box key="next:title"><Text weight="semibold">{t.sortOut}</Text></Box>
        <Box key="next:line"><Text dimColor wrap="wrap">{t.emptyPainLine}</Text></Box>
        <Button key="pain" variant="primary" hotkey="1" label={t.sortOut} onPress={() => a.draft(t.promptPain)} />
      </Box>
    )
  }

  return (
    <Box key="next" flexDirection="column" borderStyle="round" borderColor="success" width={width}>
      <Box key="next:title"><Text weight="semibold">{t.nextStep}</Text></Box>
      <Box key="next:line">
        <Text wrap="wrap">{t.nextLine(first.title) + (first.brief ? ' · ' + t.briefReady : '')}</Text>
      </Box>
      <Box key="next:buttons" flexDirection="row" flexWrap="wrap" gap={1}>
        <Button key="take" variant="primary" hotkey="1" label={t.takeFirst} onPress={() => a.draft(t.promptTake(first, stateDir))} />
        {first.brief ? (
          <Button key="brief" label={t.showBrief} variant="secondary" onPress={() => a.draft(t.promptBrief(first))} />
        ) : null}
        <Button key="backlog:show" label={t.showBacklog} variant="secondary" onPress={() => a.draft(t.promptBacklog(stateDir))} />
        <Button key="backlog:pain" label={t.ownPain} variant="secondary" onPress={() => a.draft(t.promptPain)} />
      </Box>
    </Box>
  )
}
