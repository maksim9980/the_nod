export const ROOT = 'D:\\x\\proj'
export const DIR = ROOT + '\\.nod'
export const STATE = DIR + '\\state.json'
export const NOD = ['nod'] as const

export const PANE_PROPS = {
  title: 'Nod',
  isFocused: false,
  bodyColumns: 80,
  placement: 'dock',
  scroll: { offset: 0, bodyRows: 40 },
  view: {},
} as const

import type { Review, Snapshot } from '../hooks/snapshot'

const closed = (id: string, title: string, day: number) => ({ id, title, closed_at: `2026-10-${day}T12:00:00` })
const queued = (id: string, title: string, brief: string | null = null, status = 'backlog') =>
  ({ id, title, status, brief, steps_total: 0, steps_done: 0 })

// Snapshot of the made-up project Tidepool, a small habit tracker. No `lang` key: the pane is English.
export const STATE_FULL: Snapshot = {
  schema: 1,
  generated_at: '2026-10-20T10:00:00',
  host: 'laptop',
  fresh: true,
  stale_since: null,
  waiting: [
    {
      id: 'd-fork', kind: 'fork', card: 'c-eeee',
      card_title: 'Export habits to CSV',
      question: 'Write dates to the CSV in ISO or in the local format?',
      proposed: 'ISO',
      options: ['ISO', 'Local format'],
      reason: 'Every spreadsheet reads ISO, the local format breaks sorting.',
      created: '2026-10-20T08:00:00',
    },
    {
      id: 'd-ver2', kind: 'verdict', card: 'c-cccc',
      card_title: 'Weekly email digest',
      question: 'Accept the card?', proposed: 'accept', options: ['accept', 'return'],
      reason: '', created: '2026-10-20T08:30:00',
      acceptance: {
        level: 2, result: 'solved', evidence: '3 cards of 3',
        frames: [
          { path: 'frame-1.jpg', caption: '“5 of 7 habits this week”' },
          { path: 'frame-2.jpg', caption: 'no “Unsubscribe” button' },
          { path: 'frame-3.jpg', caption: 'an email with an empty week' },
        ],
        steps: ['Open localhost:3000, sign in as demo@example.com.', 'Tick two boxes, press “Accept”.'],
        report: 'docs/briefs/2026-10-11-weekly-digest.verdict.md',
      },
    },
    {
      id: 'd-ver1', kind: 'verdict', card: 'c-dddd',
      card_title: 'Dark mode for the habit grid',
      question: 'Accept the card?', proposed: 'accept', options: ['accept', 'return'],
      reason: '', created: '2026-10-20T09:00:00',
      acceptance: {
        level: 1, result: 'unverified', evidence: 'the account has no test mailbox',
        frames: [], steps: [], report: null,
      },
    },
  ],
  running: [
    {
      card: 'c-aaaa', card_title: 'A', step: 2, step_title: 'Step 2', run: 'r-1111',
      started: '2026-10-20T09:00:00', contracts_done: 2, contracts_total: 5,
    },
  ],
  since: {
    from: '2026-10-17T00:00:00', runs: 5, steps_done: 5, accepted: 5, tokens: 25000000,
    cards_done: [
      closed('c-1001', 'Show the day streak in the profile', 18),
      closed('c-1002', 'Fix sign-in in old browsers', 18),
      closed('c-1003', 'Add the “No habits yet” screen', 19),
      closed('c-1004', 'Drop duplicate emails after a password reset', 19),
      closed('c-1005', 'Align the grid on the week page', 19),
    ],
  },
  backlog: {
    total: 44,
    top: [
      queued('c-bbbb', 'Reset the session on a password change', 'docs/briefs/2026-10-20-reset.md', 'ready'),
      queued('c-2001', 'Show the history of check-ins'),
      queued('c-2002', 'Keep an archive of habits'),
      queued('c-2003', 'Limit the number of habits per account'),
      queued('c-2004', 'Send a reminder at the end of the day'),
      queued('c-2005', 'Move the week page to the new texts'),
    ],
  },
  lock: null,
}

export const STATE_EMPTY_WAITING: Snapshot = { ...STATE_FULL, waiting: [] }

export const STATE_NO_BACKLOG: Snapshot = {
  ...STATE_FULL,
  waiting: [],
  running: [],
  since: { ...STATE_FULL.since, runs: 0, steps_done: 0, accepted: 0, tokens: 0, cards_done: [] },
  backlog: { total: 0, top: [] },
}

export const STATE_STALE: Snapshot = { ...STATE_FULL, fresh: false, stale_since: '2026-10-20T08:00:00' }

export const STATE_LOCKED: Snapshot = { ...STATE_FULL, lock: { host: 'desktop', at: '2026-10-20T09:00:00' } }

export const STATE_LEVEL3: Snapshot = {
  ...STATE_FULL,
  waiting: STATE_FULL.waiting.map(w =>
    w.id === 'd-ver2' && w.acceptance ? { ...w, acceptance: { ...w.acceptance, level: 3 as const } } : w),
}

export const REVIEW: Review = {
  week: '2026-43',
  since: '2026-10-14T00:00:00',
  until: '2026-10-21T00:00:00',
  runs: 3,
  steps_done: 2,
  stops: 1,
  accepted: 1,
  tokens: 818000,
  minutes: 36,
  suggestions: [
    { n: 1, text: 'Card c-1h5p “Export habits to CSV”: 3 brief attempts. …', status: 'proposed' },
    { n: 2, text: 'Hangs 1. …', status: 'applied' },
    { n: 3, text: 'Acceptances “not verified”: 1. …', status: 'proposed' },
  ],
  path: 'reviews/2026-43.md',
}

export const STATE_REVIEW: Snapshot = { ...STATE_FULL, review: REVIEW }

export const STATE_REVIEW_DONE: Snapshot = {
  ...STATE_FULL,
  review: { ...REVIEW, suggestions: REVIEW.suggestions.map(s => ({ ...s, status: 'applied' as const })) },
}

/** Key prefixes of the write buttons: with a stale state or a missing nod they are not on screen. */
export const WRITE_KEYS = ['opt:', 'accept:', 'return:', 'asis:', 'note:', 'free:', 'free-input:', 'free-cancel:', 'retry:', 'answer-all'] as const
