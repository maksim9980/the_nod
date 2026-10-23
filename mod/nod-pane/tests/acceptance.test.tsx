import { test, expect } from 'claude-code/testing'
import { STATE, STATE_FULL, STATE_LEVEL3, STATE_STALE } from './fixtures'
import { mountPane, runNod, seat, startSession, writeButtons } from './harness'
import type { World } from './harness'
import { fileUrl, frameUrl } from '../hooks/draw/acceptance'

const NOW = Date.parse('2026-10-20T10:12:00')
const world = (state: unknown, extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(state) }, mtime: 1, now: NOW, ...extra })
/** Color of the result line: the key is on the Box, the color on the Text inside, so the Text is found by its text. */
const resultColor = async (ui: { findAll(q: { type: string }): Promise<{ text?: string; props: Record<string, unknown> }[]> }, text: string) =>
  (await ui.findAll({ type: 'Text' })).find(t => t.text === text)?.props.color

const decisionRuns = (runs: (readonly string[])[]) => runs.filter(r => r.includes('decision'))

/** STATE_FULL where the acceptance fields of d-ver2 are replaced. */
const withAcceptance = (patch: object) => ({
  ...STATE_FULL,
  waiting: STATE_FULL.waiting.map(w =>
    w.id === 'd-ver2' && w.acceptance ? { ...w, acceptance: { ...w.acceptance, ...patch } } : w),
})

test('frameUrl and fileUrl: the separator by the folder, an absolute path is not joined', () => {
  const dir = 'D:\\x\\proj\\.nod'
  expect(frameUrl(dir, 'c-cccc', 'frame-1.jpg')).toBe('file:///D:/x/proj/.nod/acceptance/c-cccc/frame-1.jpg')
  expect(frameUrl(dir, 'c-cccc', 'D:\\shots\\big.png')).toBe('file:///D:/shots/big.png')
  expect(frameUrl('/home/u/proj/.nod', 'c-1', 'a b.png'))
    .toBe('file:///home/u/proj/.nod/acceptance/c-1/a%20b.png')
  expect(frameUrl('/home/u/proj/.nod', 'c-1', '/tmp/a b.png')).toBe('file:///tmp/a%20b.png')
  expect(frameUrl(dir, 'c-1', 'a (1)#2.png')).toBe('file:///D:/x/proj/.nod/acceptance/c-1/a%20%281%29%232.png')
  expect(fileUrl(dir, 'docs/briefs/r.verdict.md')).toBe('file:///D:/x/proj/docs/briefs/r.verdict.md')
  expect(fileUrl(dir, 'D:\\r\\rapport é.md')).toBe('file:///D:/r/' + encodeURI('rapport é.md'))
})

for (const surface of ['desktop', 'terminal'] as const) {
  test(`level 2: frames as Markdown with file: links, Confirm writes accept on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    const md = await ui.find({ key: 'frames:d-ver2' })
    expect(md?.props.text).toContain('](file:///D:/x/proj/.nod/acceptance/c-cccc/frame-1.jpg)')
    expect(md?.props.text).toContain('see: “5 of 7 habits this week”')
    expect((await ui.find({ key: 'res:d-ver2' }))?.text).toBe('Acceptance: solved — 3 cards of 3')
    expect(await resultColor(ui, 'Acceptance: solved — 3 cards of 3')).toBe('success')
    expect((await ui.find({ key: 'accept:d-ver2' }))?.props)
      .toMatchObject({ variant: 'primary', label: 'Confirm — close' })
    expect((await ui.find({ key: 'return:d-ver2' }))?.props.variant).not.toBe('primary')
    await ui.press({ key: 'accept:d-ver2' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)[0]?.slice(-2)).toEqual(['d-ver2', 'accept'])
    expect(calls.statuses).toContain('Nod: pressed “Confirm — close”…')
  })

  test(`return: Input "What is wrong", Enter writes return --note on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'return:d-ver2' })
    await calls.clock.settle()
    expect(await ui.find({ key: 'accept:d-ver2' })).toBeUndefined()
    expect((await ui.find({ key: 'note:d-ver2' }))?.props)
      .toMatchObject({ label: 'What is wrong', submitLabel: 'return' })
    await ui.input({ key: 'note:d-ver2', text: '   ' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)).toHaveLength(0)
    await ui.input({ key: 'note:d-ver2', text: 'the button is not on screen' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)[0]).toEqual(runNod(['decision', 'answer', '--note', 'the button is not on screen', '--', 'd-ver2', 'return']))
    expect(await ui.find({ key: 'note:d-ver2' })).toBeUndefined()
  })

  test(`cancelling a return closes the field and brings the buttons back on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'return:d-ver2' })
    await calls.clock.settle()
    await ui.press({ key: 'free-cancel:d-ver2' })
    await calls.clock.settle()
    expect(await ui.find({ key: 'note:d-ver2' })).toBeUndefined()
    expect(await ui.find({ key: 'accept:d-ver2' })).toBeDefined()
  })

  test(`level 1 "not verified": warning, "Accept as is" primary, "Suggest a way to check" drafts a prompt on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await resultColor(ui, 'Acceptance: not verified — the account has no test mailbox')).toBe('warning')
    expect((await ui.find({ key: 'res:d-ver1' }))?.text).toBe('Acceptance: not verified — the account has no test mailbox')
    expect((await ui.find({ key: 'asis:d-ver1' }))?.props)
      .toMatchObject({ variant: 'primary', label: 'Accept as is' })
    expect(await ui.find({ key: 'frames:d-ver1' })).toBeUndefined()
    await ui.press({ key: 'verify:d-ver1' })
    await calls.clock.settle()
    const draft = (await ui.find({ key: 'draft' }))?.text ?? ''
    expect(draft).toContain('c-dddd')
    expect(draft).toContain('no test mailbox')
    await ui.press({ key: 'asis:d-ver1' })
    await calls.clock.settle()
    expect(decisionRuns(calls.runs)[0]?.slice(-2)).toEqual(['d-ver1', 'accept'])
  })

  test(`"not solved": error, return is primary, accept as is is second on ${surface}`, async ($, on) => {
    const calls = seat(on, world(withAcceptance({ result: 'unsolved' })))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await resultColor(ui, 'Acceptance: not solved — 3 cards of 3')).toBe('error')
    expect((await ui.find({ key: 'return:d-ver2' }))?.props).toMatchObject({ variant: 'primary', label: 'Not right — return' })
    expect((await ui.find({ key: 'asis:d-ver2' }))?.props.variant).not.toBe('primary')
    expect(await ui.find({ key: 'accept:d-ver2' })).toBeUndefined()
    expect(await ui.find({ key: 'verify:d-ver2' })).toBeUndefined()
  })

  test(`"Suggest a way to check" stays when stale, no write buttons on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_STALE))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'verify:d-ver1' })).toBeDefined()
    expect(await writeButtons(ui)).toHaveLength(0)
    await ui.press({ key: 'verify:d-ver1' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'draft' }))?.text).toContain('c-dddd')
  })

  test(`More opens the report, Less hides it on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'report:d-ver2' })).toBeUndefined()
    expect((await ui.find({ key: 'more:d-ver2' }))?.props.label).toBe('More')
    await ui.press({ key: 'more:d-ver2' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'report:d-ver2' }))?.props.text)
      .toContain('file:///D:/x/proj/docs/briefs/2026-10-11-weekly-digest.verdict.md')
    expect((await ui.find({ key: 'dec:d-ver2' }))?.text).toContain('1. Open localhost:3000')
    expect((await ui.find({ key: 'more:d-ver2' }))?.props.label).toBe('Less')
    expect(await ui.find({ key: 'frames:d-ver2' })).toBeDefined()
    await ui.press({ key: 'more:d-ver2' })
    await calls.clock.settle()
    expect(await ui.find({ key: 'report:d-ver2' })).toBeUndefined()
    expect((await ui.find({ key: 'dec:d-ver2' }))?.text).not.toContain('1. Open')
  })

  test(`level 3 — the steps are numbered on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_LEVEL3))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    const text = (await ui.find({ key: 'dec:d-ver2' }))?.text ?? ''
    expect(text).toContain('By hand · 2 steps')
    expect(text).toContain('1. Open localhost:3000')
    expect(text).toContain('2. Tick two boxes')
    expect(await ui.find({ key: 'frames:d-ver2' })).toBeUndefined()
  })

  test(`an absolute frame path is not joined with the acceptance folder on ${surface}`, async ($, on) => {
    const frames = [{ path: 'D:\\shots\\big.png', caption: 'big' }]
    const calls = seat(on, world(withAcceptance({ frames })))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    const text = String((await ui.find({ key: 'frames:d-ver2' }))?.props.text)
    expect(text).toContain('](file:///D:/shots/big.png)')
    expect(text).not.toContain('acceptance')
  })

  test(`a caption ending in "\\" does not break the link on ${surface}`, async ($, on) => {
    const frames = [{ path: 'frame-1.jpg', caption: 'end\\' }]
    const calls = seat(on, world(withAcceptance({ frames })))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    const text = String((await ui.find({ key: 'frames:d-ver2' }))?.props.text)
    expect(text).toContain('end\\\\](file:///')
    expect(text).toContain('— see: end\\\\')
  })

  test(`six frames with long captions pass validation on ${surface}`, async ($, on) => {
    const frames = Array.from({ length: 6 }, (_, i) => ({ path: `f${i}.jpg`, caption: String(i).repeat(300) }))
    const calls = seat(on, world(withAcceptance({ frames })))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'dec:d-ver2' }))?.text).toContain('Look at the frames · 6')
    expect(String((await ui.find({ key: 'frames:d-ver2' }))?.props.text))
      .toContain('](file:///D:/x/proj/.nod/acceptance/c-cccc/f5.jpg)')
  })

  test(`a refused verdict write: err and Retry on the card on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, {
      run: argv => (argv.includes('decision') ? { exitCode: 2, stderr: 'error: failure\n' } : {}),
    }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'accept:d-ver2' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'err:d-ver2' }))?.text).toBe('not saved: failure')
    expect(await ui.find({ key: 'retry:d-ver2' })).toBeDefined()
  })
}
