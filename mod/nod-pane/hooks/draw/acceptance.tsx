import type { RenderElement } from 'claude-code'

import type { Actions } from '../actions'
import { sepOf } from '../find'
import type { Acceptance, Waiting } from '../snapshot'
import type { Texts } from '../texts/index'
import type { DecisionCtx } from './waiting'
import type { Ui } from './ui'
import { drawBusy, drawFailure } from './write-state'

const RESULT_COLOR = { solved: 'success', unsolved: 'error', unverified: 'warning' } as const

export const levelOf = (d: Waiting): 1 | 2 | 3 => d.acceptance?.level ?? 1

const isAbsolute = (path: string): boolean => path[1] === ':' || path.startsWith('/')

/** `file:` address of a path: `\` to `/`, then encodeURI; brackets, `#` and `?` are encoded by hand, or they break Markdown and the address. */
function toUrl(path: string): string {
  const slashed = path.replace(/\\/g, '/')
  const encoded = encodeURI(slashed).replace(/[()#?]/g, c => '%' + c.charCodeAt(0).toString(16).toUpperCase())

  return (slashed.startsWith('/') ? 'file://' : 'file:///') + encoded
}

/** Address of a frame: a relative path lies in `<stateDir>/acceptance/<card>/`, an absolute one is taken as is. */
export function frameUrl(stateDir: string, card: string, framePath: string): string {
  if (isAbsolute(framePath)) return toUrl(framePath)
  const sep = sepOf(stateDir)

  return toUrl([stateDir, 'acceptance', card, framePath].join(sep))
}

/** Address of a file: a relative path counts from the parent of `stateDir` (the project root). */
export function fileUrl(stateDir: string, relOrAbs: string): string {
  if (isAbsolute(relOrAbs)) return toUrl(relOrAbs)
  const sep = sepOf(stateDir)
  const root = stateDir.replace(/[\\/]+$/, '')

  return toUrl(root.slice(0, Math.max(0, root.lastIndexOf(sep))) + sep + relOrAbs)
}

const fileName = (path: string): string => path.slice(path.search(/[^\\/]*$/))
const plain = (text: string): string => text.replace(/\s+/g, ' ').replace(/[\\[\]]/g, '\\$&')

/** A frame: a picture with a caption and a link to the file — the link stays if Markdown does not draw the picture. */
function framesMarkdown(t: Texts, d: Waiting, a: Acceptance, stateDir: string): string {
  return a.frames.map(f => {
    const url = frameUrl(stateDir, d.card ?? '', f.path)
    const caption = plain(f.caption)

    return '![' + t.see + ': ' + caption + '](' + url + ')  \n[' + plain(fileName(f.path)) + '](' + url + ') — ' + t.see + ': ' + caption
  }).join('\n\n')
}

function drawFrames(ui: Ui, t: Texts, d: Waiting, a: Acceptance, stateDir: string): RenderElement[] {
  const { Box, Text, Markdown } = ui

  return [
    <Box key={'frames-title:' + d.id}><Text size="caption" mono dimColor>{t.framesTitle(a.frames.length)}</Text></Box>,
    <Markdown key={'frames:' + d.id} text={framesMarkdown(t, d, a, stateDir)} />,
  ]
}

function drawSteps(ui: Ui, t: Texts, d: Waiting, a: Acceptance): RenderElement[] {
  const { Box, Text } = ui

  return [
    <Box key={'steps-title:' + d.id}><Text size="caption" mono dimColor>{t.stepsTitle(a.steps.length)}</Text></Box>,
    <Box key={'steps:' + d.id} flexDirection="column">
      {a.steps.map((step, i) => <Box key={'step:' + d.id + ':' + i}><Text wrap="wrap">{i + 1}. {step}</Text></Box>)}
    </Box>,
  ]
}

/** The part of its own level is always seen; the other non-empty parts and the report — by "More". */
function drawBody(ui: Ui, d: Waiting, a: Acceptance, ctx: DecisionCtx): RenderElement[] {
  const { Markdown } = ui
  const { t } = ctx
  const level = levelOf(d)
  const own = level === 2 ? drawFrames(ui, t, d, a, ctx.stateDir) : level === 3 ? drawSteps(ui, t, d, a) : []
  const extra = [
    ...(level !== 2 && a.frames.length > 0 ? drawFrames(ui, t, d, a, ctx.stateDir) : []),
    ...(level !== 3 && a.steps.length > 0 ? drawSteps(ui, t, d, a) : []),
    ...(a.report === null ? [] : [
      <Markdown key={'report:' + d.id} text={'[' + t.report + '](' + fileUrl(ctx.stateDir, a.report) + ')'} />,
    ]),
  ]

  return ctx.expanded.includes(d.id) ? [...own, ...extra] : own
}

function hasMore(d: Waiting, a: Acceptance): boolean {
  const level = levelOf(d)

  return a.report !== null || (level !== 2 && a.frames.length > 0) || (level !== 3 && a.steps.length > 0)
}

function drawReturn(ui: Ui, t: Texts, d: Waiting, a: Actions): RenderElement[] {
  const { Input, Button } = ui

  return [
    <Input
      key={'note:' + d.id}
      label={t.whatWrong}
      submitLabel={t.returnSubmit}
      onSubmit={(text: string) => {
        const note = text.trim()
        if (note !== '') a.answer(d.id, 'return', { note, label: t.returnSubmit })
      }}
    />,
    <Button key={'free-cancel:' + d.id} label={t.cancel} variant="secondary" onPress={() => a.openFree(null)} />,
  ]
}

/** Buttons by the result: one primary — the likeliest move; "return" is never green. */
function drawVerdictButtons(
  ui: Ui, t: Texts, d: Waiting, index: number, result: Acceptance['result'], a: Actions,
): RenderElement[] {
  const { Button } = ui
  const hotkey = index === 0 ? '1' : undefined
  const accept = (key: string, label: string, primary: boolean) => (
    <Button
      key={key + ':' + d.id}
      label={label}
      variant={primary ? 'primary' : 'secondary'}
      hotkey={primary ? hotkey : undefined}
      onPress={() => a.answer(d.id, 'accept', { label })}
    />
  )
  const back = (primary: boolean) => (
    <Button
      key={'return:' + d.id}
      label={t.returnLabel}
      variant={primary ? 'primary' : 'secondary'}
      hotkey={primary ? hotkey : undefined}
      onPress={() => a.openFree(d.id)}
    />
  )
  if (result === 'solved') return [accept('accept', t.acceptClose, true), back(false)]
  if (result === 'unverified') return [accept('asis', t.acceptAsIs, true)]

  return [back(true), accept('asis', t.acceptAsIs, false)]
}

function drawActions(ui: Ui, d: Waiting, index: number, a: Acceptance, ctx: DecisionCtx, act: Actions): RenderElement[] {
  const { Button } = ui
  const { t } = ctx
  const out: RenderElement[] = []
  if (ctx.pending === d.id) {
    out.push(drawBusy(ui, t, d))
  } else if (ctx.canWrite && ctx.pending === null) {
    out.push(...(ctx.freeFor === d.id ? drawReturn(ui, t, d, act) : drawVerdictButtons(ui, t, d, index, a.result, act)))
  }
  if (a.result === 'unverified') {
    out.push(<Button key={'verify:' + d.id} label={t.giveWay} variant="secondary" onPress={() => act.draft(t.promptVerify(d))} />)
  }

  return out
}

/** The acceptance card: the result, the content by level, the buttons by result. */
export function drawVerdict(
  ui: Ui, d: Waiting, index: number, ctx: DecisionCtx, act: Actions, width: number,
): RenderElement {
  const { Box, Text, Button } = ui
  const { t } = ctx
  const a: Acceptance = d.acceptance ?? { level: 1, result: 'unverified', evidence: '', frames: [], steps: [], report: null }
  const opened = ctx.expanded.includes(d.id)

  return (
    <Box key={'dec:' + d.id} flexDirection="column" borderStyle="round" borderColor="success" width={width}>
      <Box key={'title:' + d.id}>
        <Text weight="semibold" wrap="wrap">{d.card_title ?? d.question}</Text>
      </Box>
      <Box key={'res:' + d.id}>
        <Text color={RESULT_COLOR[a.result]} wrap="wrap">
          {t.acceptor + ': ' + t.resultLabel(a.result) + (a.evidence === '' ? '' : ' — ' + a.evidence)}
        </Text>
      </Box>
      {drawBody(ui, d, a, ctx)}
      {hasMore(d, a)
        ? <Button key={'more:' + d.id} label={opened ? t.lessLabel : t.moreLabel} variant="secondary" onPress={() => act.toggle(d.id)} />
        : null}
      {drawActions(ui, d, index, a, ctx, act)}
      {drawFailure(ui, d, ctx, act)}
    </Box>
  )
}
