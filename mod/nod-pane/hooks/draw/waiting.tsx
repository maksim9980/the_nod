import type { RenderElement } from 'claude-code'

import type { Actions } from '../actions'
import { inBatch } from '../snapshot'
import type { Waiting } from '../snapshot'
import type { Progress, WriteError } from '../state'
import { clip } from '../texts/index'
import type { Texts } from '../texts/index'
import { drawVerdict } from './acceptance'
import type { Ui } from './ui'
import { drawBusy, drawFailure } from './write-state'

export type WaitingModel = {
  items: Waiting[]
  canWrite: boolean
  pending: string | null
  progress: Progress | null
  writeError: WriteError | null
  expanded: string[]
  freeFor: string | null
  stateDir: string
  t: Texts
}

export type DecisionCtx = Omit<WaitingModel, 'items'>

/**
 * Kinds whose options are canonical values (the_nod/vocab.py) and get a caption of the language. Options of a fork
 * and of brief-yes are free text: an option "no" there stays "no".
 */
const CANONICAL: ReadonlySet<Waiting['kind']> = new Set(['owner-action', 'next-batch', 'pain', 'return', 'run-stuck'])

/** Caption of an option: a canonical answer by the dictionary, any other text as is; clipped to LABEL_MAX. */
const captionOf = (t: Texts, d: Waiting, value: string): string => clip(CANONICAL.has(d.kind) ? t.answerLabel(value) : value)

/** `caption` — the option's caption (the "pressed …" line writes it), `label` — the button label: the proposed one with a suffix. */
type Choice = { value: string; caption: string; label: string; free: boolean; primary: boolean }

/** Buttons by `options` in their order; a `proposed` outside the list comes first and is written with `--free`. */
function choices(t: Texts, d: Waiting): Choice[] {
  const listed = d.options.map(value => {
    const caption = captionOf(t, d, value)

    return { value, caption, label: caption, free: false, primary: value === d.proposed }
  })
  const primaryAt = listed.findIndex(c => c.primary)
  const marked = listed.map((c, i) => ({
    ...c,
    primary: i === primaryAt,
    label: i === primaryAt ? c.label + t.proposedSuffix : c.label,
  }))
  if (primaryAt !== -1 || d.proposed === '') return marked

  const caption = captionOf(t, d, d.proposed)

  return [{ value: d.proposed, caption, label: caption + t.proposedSuffix, free: true, primary: true }, ...marked]
}

function drawChoices(ui: Ui, t: Texts, d: Waiting, index: number, a: Actions): RenderElement {
  const { Box, Button } = ui

  return (
    <Box key={'opts:' + d.id} flexDirection="row" flexWrap="wrap" gap={1}>
      {choices(t, d).map((c, i) => (
        <Button
          key={'opt:' + d.id + ':' + i}
          label={c.label}
          variant={c.primary ? 'primary' : 'secondary'}
          hotkey={c.primary && index === 0 ? '1' : undefined}
          onPress={() => a.answer(d.id, c.value, c.free ? { free: true, label: c.caption } : { label: c.caption })}
        />
      ))}
    </Box>
  )
}

function drawFreeOpen(ui: Ui, t: Texts, d: Waiting, a: Actions): RenderElement {
  const { Button } = ui

  return <Button key={'free:' + d.id} label={t.free} variant="secondary" onPress={() => a.openFree(d.id)} />
}

/** The own answer field: empty after trim() is not written, "Cancel" closes the field. */
function drawFree(ui: Ui, t: Texts, d: Waiting, a: Actions): RenderElement[] {
  const { Input, Button } = ui

  return [
    <Input
      key={'free-input:' + d.id}
      label={t.free}
      placeholder={t.freePlaceholder}
      submitLabel={t.freeSubmit}
      onSubmit={(text: string) => {
        const answer = text.trim()
        if (answer !== '') a.answer(d.id, answer, { free: true, label: clip(answer) })
      }}
    />,
    <Button key={'free-cancel:' + d.id} label={t.cancel} variant="secondary" onPress={() => a.openFree(null)} />,
  ]
}

function drawWriteState(ui: Ui, d: Waiting, index: number, ctx: DecisionCtx, a: Actions): RenderElement[] {
  const { t } = ctx
  const out: RenderElement[] = []
  if (ctx.pending === d.id) {
    out.push(drawBusy(ui, t, d))
  } else if (ctx.canWrite && ctx.pending === null) {
    out.push(...(ctx.freeFor === d.id ? drawFree(ui, t, d, a) : [drawChoices(ui, t, d, index, a), drawFreeOpen(ui, t, d, a)]))
  }
  out.push(...drawFailure(ui, d, ctx, a))

  return out
}

/** A decision card of any kind; verdicts are drawn by `drawVerdict`. */
export function drawDecision(
  ui: Ui, d: Waiting, index: number, ctx: DecisionCtx, a: Actions, width: number,
): RenderElement {
  if (d.kind === 'verdict') return drawVerdict(ui, d, index, ctx, a, width)
  const { Box, Text } = ui
  const action = d.kind === 'owner-action'
  const border = action ? 'warning' : 'success'

  // owner-action: a warning frame and the "Action needed" label above the question.
  return (
    <Box key={'dec:' + d.id} flexDirection="column" borderStyle="round" borderColor={border} width={width}>
      {action ? (
        <Box key={'label:' + d.id}>
          <Text color="warning" weight="semibold">{ctx.t.needsAction}</Text>
        </Box>
      ) : null}
      <Box key={'q:' + d.id}>
        <Text weight="semibold" wrap="wrap">{d.question}</Text>
      </Box>
      {d.card_title === null ? null : (
        <Box key={'title:' + d.id}>
          <Text dimColor wrap="wrap">{d.card_title}</Text>
        </Box>
      )}
      {d.reason === '' ? null : (
        <Box key={'reason:' + d.id}>
          <Text dimColor wrap="wrap">{d.reason}</Text>
        </Box>
      )}
      {drawWriteState(ui, d, index, ctx, a)}
    </Box>
  )
}

/** "Accept all" above the cards: needs two or more decisions with a proposed answer; during the batch — a progress line. */
function drawAll(ui: Ui, m: WaitingModel, a: Actions): RenderElement | null {
  const { Box, Text, Button } = ui
  const total = m.items.filter(inBatch).length
  // The batch first: the core rebuilds the snapshot after each answer, and fewer than two stay waiting.
  if (m.pending === 'all') {
    const done = m.progress?.done ?? 0

    return <Box key="busy:all"><Text dimColor>{m.t.busyAll(done + 1, m.progress?.total ?? total)}</Text></Box>
  }
  if (total < 2) return null
  if (!m.canWrite || m.pending !== null) return null

  return <Button key="answer-all" label={m.t.answerAll} variant="primary" hotkey="a" onPress={() => a.answerAll()} />
}

/** owner-action first: while it is open, the work stands; the rest in the snapshot order. */
function ownerActionsFirst(items: readonly Waiting[]): Waiting[] {
  return [...items.filter(d => d.kind === 'owner-action'), ...items.filter(d => d.kind !== 'owner-action')]
}

/** Cards of the zone; an empty zone is drawn by `drawZone` in pane.tsx. */
export function drawWaiting(ui: Ui, m: WaitingModel, a: Actions, width: number): RenderElement {
  const { Box } = ui
  const { items, ...ctx } = m

  return (
    <Box key="waiting:cards" flexDirection="column" gap={1}>
      {drawAll(ui, m, a)}
      {ownerActionsFirst(items).map((d, i) => drawDecision(ui, d, i, ctx, a, width))}
    </Box>
  )
}
