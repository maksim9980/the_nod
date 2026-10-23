import { test, expect } from 'claude-code/testing'
import { DIR, STATE, STATE_EMPTY_WAITING, STATE_FULL, STATE_NO_BACKLOG, STATE_STALE } from './fixtures'
import { mountPane, seat, startSession } from './harness'
import type { World } from './harness'
import { EN } from '../hooks/texts/index'

const NOW = Date.parse('2026-10-20T10:12:00')

const world = (state: unknown, extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(state) }, mtime: 1, now: NOW, ...extra })

const SHOW_PROMPT = 'Show the whole project backlog: run nod --root ' + DIR + ' status --peek and list the cards in order with their statuses.'
const PROMPT_PAIN = EN.promptPain

for (const surface of ['desktop', 'terminal'] as const) {
  test(`top of the backlog: five lines, brief ready, 39 more, the button drafts a prompt on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    for (const c of STATE_FULL.backlog.top.slice(0, 5)) expect(await ui.find({ key: 'bl:' + c.id })).toBeDefined()
    expect(await ui.find({ key: 'bl:' + STATE_FULL.backlog.top[5]?.id })).toBeUndefined()
    expect((await ui.find({ key: 'bl:c-bbbb' }))?.text).toContain('brief ready')
    expect((await ui.find({ key: 'bl:c-2001' }))?.text).not.toContain('brief ready')
    expect((await ui.find({ key: 'backlog:more' }))?.text).toBe('39 more')
    expect(await ui.find({ key: 'footer' })).toBeUndefined()
    await ui.press({ key: 'backlog:show' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'draft' }))?.text).toBe(SHOW_PROMPT)
  })

  test(`the draft grows with a space, Send calls prompt.submit and clears it on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'backlog:show' })
    await ui.press({ key: 'backlog:pain' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'draft' }))?.text).toMatch(/statuses\. Sort out what hurts/)
    expect((await ui.find({ key: 'send' }))?.props).toMatchObject({ variant: 'primary', hotkey: 's' })
    await ui.press({ key: 'send' })
    await calls.clock.settle()
    expect(calls.prompts).toHaveLength(1)
    expect(calls.prompts[0]).toContain('nod card add')
    expect(calls.prompts[0]).toBe(SHOW_PROMPT + ' ' + PROMPT_PAIN)
    expect(await ui.find({ key: 'footer' })).toBeUndefined()
  })

  test(`a refused prompt.submit keeps the draft on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, { submitDeny: 'the queue is closed' }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'backlog:pain' })
    await ui.press({ key: 'send' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'draft' }))?.text).toBe(PROMPT_PAIN)
    expect(calls.prompts).toHaveLength(0)
  })

  test(`a second Send while sending sends nothing on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, { submitDelay: 500 }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'backlog:pain' })
    await calls.clock.settle()
    await ui.press({ key: 'send' })
    await ui.press({ key: 'send' })
    await calls.clock.advance(500)
    await calls.clock.settle()
    expect(calls.prompts).toHaveLength(1)
    expect(await ui.find({ key: 'footer' })).toBeUndefined()
  })

  test(`text added while sending stays in the draft on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL, { submitDelay: 500 }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'backlog:pain' })
    await calls.clock.settle()
    await ui.press({ key: 'send' })
    await ui.press({ key: 'backlog:show' })
    await calls.clock.advance(500)
    await calls.clock.settle()
    expect(calls.prompts).toEqual([PROMPT_PAIN])
    expect((await ui.find({ key: 'draft' }))?.text).toBe(SHOW_PROMPT)
  })

  test(`Clear drops the draft without sending; the draft lives through rereads and stale on ${surface}`, async ($, on) => {
    const w = world(STATE_FULL)
    const calls = seat(on, w)
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'backlog:pain' })
    await calls.clock.settle()
    w.mtime = 2
    await calls.clock.advance(15000)
    await calls.clock.settle()
    expect((await ui.find({ key: 'draft' }))?.text).toBe(PROMPT_PAIN)
    await ui.press({ key: 'clear' })
    await calls.clock.settle()
    expect(await ui.find({ key: 'footer' })).toBeUndefined()
    expect(calls.prompts).toHaveLength(0)

    w.files[STATE] = JSON.stringify(STATE_STALE)
    w.mtime = 3
    await calls.clock.advance(15000)
    await calls.clock.settle()
    expect(await ui.find({ key: 'stale' })).toBeDefined()
    await ui.press({ key: 'backlog:show' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'draft' }))?.text).toBe(SHOW_PROMPT)
    expect(await ui.find({ key: 'footer' })).toBeDefined()
  })

  test(`no decisions — "Next step", "Take the first card" drafts a prompt with the id, path and brief on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_EMPTY_WAITING))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'next' }))?.text)
      .toContain('No decisions. Top of the backlog: “Reset the session on a password change” · brief ready')
    expect((await ui.find({ key: 'take' }))?.props).toMatchObject({ variant: 'primary', hotkey: '1' })
    expect(await ui.find({ key: 'brief' })).toBeDefined()
    await ui.press({ key: 'take' })
    await calls.clock.settle()
    const draft = (await ui.find({ key: 'draft' }))?.text ?? ''
    expect(draft).toContain('c-bbbb')
    expect(draft).toContain(DIR + '\\cards\\')
    expect(draft).toContain('docs/briefs/2026-10-20-reset.md')
    expect(draft).toContain('nod run start c-bbbb')
    expect(await ui.findAll({ key: 'backlog:show' })).toHaveLength(1)
    expect(await ui.findAll({ key: 'backlog:pain' })).toHaveLength(1)
    await ui.press({ key: 'brief' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'draft' }))?.text).toContain('Open the brief docs/briefs/2026-10-20-reset.md and sum up')
  })

  test(`the first card without a brief — the prompt asks to write one on ${surface}`, async ($, on) => {
    const top = STATE_EMPTY_WAITING.backlog.top.slice(1)
    const calls = seat(on, world({ ...STATE_EMPTY_WAITING, backlog: { total: 43, top } }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'brief' })).toBeUndefined()
    await ui.press({ key: 'take' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'draft' }))?.text).toContain('nod decision ask --kind fork --card c-2001')
  })

  test(`an empty backlog — "Sort out what hurts" on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_NO_BACKLOG))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'backlog:empty' }))?.text).toBe('The backlog is empty')
    expect(await ui.find({ key: 'backlog:show' })).toBeUndefined()
    expect((await ui.find({ key: 'pain' }))?.props).toMatchObject({ variant: 'primary', hotkey: '1' })
    await ui.press({ key: 'pain' })
    await calls.clock.settle()
    expect((await ui.find({ key: 'draft' }))?.text).toBe(PROMPT_PAIN)
  })

  test(`with decisions there is no "Next step" card, the backlog buttons are in the backlog zone on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_FULL))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'next' })).toBeUndefined()
    expect(await ui.find({ key: 'take' })).toBeUndefined()
    expect(await ui.findAll({ key: 'backlog:show' })).toHaveLength(1)
    expect(await ui.findAll({ key: 'backlog:pain' })).toHaveLength(1)
  })
}
