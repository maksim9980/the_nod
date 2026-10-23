import { test, expect } from 'claude-code/testing'
import { DIR, REVIEW, STATE, STATE_FULL, STATE_REVIEW, STATE_REVIEW_DONE } from './fixtures'
import { mountPane, seat, startSession } from './harness'
import type { World } from './harness'

const NOW = Date.parse('2026-10-20T10:12:00')

const world = (state: unknown, extra: Partial<World> = {}): World =>
  ({ files: { [STATE]: JSON.stringify(state) }, mtime: 1, now: NOW, ...extra })

const suggestion = (n: number) => ({ n, text: 'Item ' + n, status: 'proposed' as const })

for (const surface of ['desktop', 'terminal'] as const) {
  test(`the review zone: the week in the title, period, counters, three lines, statuses, frame and button on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_REVIEW))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'zone:review:title' }))?.text).toBe('Weekly review · 2026-43')
    expect((await ui.find({ key: 'review:period' }))?.text).toBe('Oct 14 — Oct 21')
    expect((await ui.find({ key: 'review:counters' }))?.text)
      .toBe('runs 3 · steps 2 · stops 1 · accepted 1 · tokens 818 K · 36 min')
    const first = (await ui.find({ key: 'rv:1' }))?.text
    expect(first).toContain('1. Card c-1h5p')
    expect(first).toContain('· proposed')
    expect((await ui.find({ key: 'rv:2' }))?.text).toContain('· applied')
    expect(await ui.find({ key: 'rv:3' })).toBeDefined()
    expect((await ui.find({ key: 'review:list' }))?.props).toMatchObject({ borderColor: 'success' })
    expect((await ui.find({ key: 'review:apply' }))?.props).toMatchObject({ variant: 'primary', label: 'Apply the suggestions' })
    expect(await ui.find({ key: 'review:empty' })).toBeUndefined()
  })

  test(`Apply the suggestions drafts a prompt with the week, the path, items 1, 3 and review mark on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_REVIEW))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    await ui.press({ key: 'review:apply' })
    await calls.clock.settle()
    const draft = (await ui.find({ key: 'draft' }))?.text ?? ''
    expect(draft).toContain('2026-43')
    expect(draft).toContain(DIR + '\\reviews\\2026-43.md')
    expect(draft).toContain('“What to improve”, items 1, 3')
    expect(draft).toContain('nod --root ' + DIR + ' review mark 2026-43 <number> --applied')
    expect(calls.prompts).toHaveLength(0)
  })

  test(`all applied — no frame and no button on ${surface}`, async ($, on) => {
    const calls = seat(on, world(STATE_REVIEW_DONE))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'zone:review:title' }))?.text).toBe('Weekly review · 2026-43')
    expect(await ui.find({ key: 'review:apply' })).toBeUndefined()
    expect((await ui.find({ key: 'review:list' }))?.props?.borderColor).toBeUndefined()
    expect((await ui.find({ key: 'rv:1' }))?.text).toContain('· applied')
  })

  for (const [label, state] of [['without the key', STATE_FULL], ['review: null', { ...STATE_FULL, review: null }]] as const) {
    test(`no review (${label}) — "No review yet: nod review week", the title "· —" on ${surface}`, async ($, on) => {
      const calls = seat(on, world(state))
      await startSession(calls, $)
      const ui = await mountPane($, surface)
      expect((await ui.find({ key: 'zone:review:title' }))?.text).toBe('Weekly review · —')
      expect((await ui.find({ key: 'review:empty' }))?.text).toBe('No review yet: nod review week')
      expect(await ui.find({ key: 'review:list' })).toBeUndefined()
      expect(await ui.find({ key: 'review:apply' })).toBeUndefined()
      expect(await ui.find({ key: 'load-error' })).toBeUndefined()
    })
  }

  test(`review.suggestions is not an array — the load error names the field on ${surface}`, async ($, on) => {
    const calls = seat(on, world({ ...STATE_FULL, review: { ...REVIEW, suggestions: 'none' } }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect((await ui.find({ key: 'load-error' }))?.text).toContain('review.suggestions')
    expect(await ui.find({ key: 'zone:review:title' })).toBeUndefined()
  })

  test(`more than five suggestions — "N more" on ${surface}`, async ($, on) => {
    const seven = { ...REVIEW, suggestions: [1, 2, 3, 4, 5, 6, 7].map(suggestion) }
    const calls = seat(on, world({ ...STATE_FULL, review: seven }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    for (const n of [1, 2, 3, 4, 5]) expect(await ui.find({ key: 'rv:' + n })).toBeDefined()
    expect(await ui.find({ key: 'rv:6' })).toBeUndefined()
    expect((await ui.find({ key: 'review:more' }))?.text).toBe('2 more')
  })

  test(`review:apply is not a write button: it stays when stale on ${surface}`, async ($, on) => {
    const calls = seat(on, world({ ...STATE_REVIEW, fresh: false, stale_since: '2026-10-20T08:00:00' }))
    await startSession(calls, $)
    const ui = await mountPane($, surface)
    expect(await ui.find({ key: 'stale' })).toBeDefined()
    expect(await ui.find({ key: 'review:apply' })).toBeDefined()
  })
}
