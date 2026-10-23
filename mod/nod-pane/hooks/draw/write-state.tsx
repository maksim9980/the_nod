import type { RenderElement } from 'claude-code'

import type { Actions } from '../actions'
import type { Waiting } from '../snapshot'
import type { WriteError } from '../state'
import type { Texts } from '../texts/index'
import type { Ui } from './ui'

type WriteCtx = { canWrite: boolean; pending: string | null; writeError: WriteError | null; t: Texts }

/** The "saving…" line on the card being written now. */
export function drawBusy(ui: Ui, t: Texts, d: Waiting): RenderElement {
  const { Box, Text } = ui

  return <Box key={'busy:' + d.id}><Text dimColor>{t.busy}</Text></Box>
}

/** A write error next to the card and "Retry" once writing is possible again. */
export function drawFailure(ui: Ui, d: Waiting, ctx: WriteCtx, a: Actions): RenderElement[] {
  const { Box, Text, Button } = ui
  if (ctx.writeError?.id !== d.id) return []
  const out: RenderElement[] = [
    <Box key={'err:' + d.id}>
      <Text color="error" wrap="wrap">{ctx.t.notWritten(ctx.writeError.message)}</Text>
    </Box>,
  ]
  if (ctx.pending === null && ctx.canWrite) {
    out.push(<Button key={'retry:' + d.id} label={ctx.t.retry} variant="secondary" onPress={() => a.retry()} />)
  }

  return out
}
