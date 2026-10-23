// English texts of the pane and of /nod: the default language and the shape every dictionary follows.
import { sepOf } from '../find'
import type { Review, ReviewSuggestion } from '../snapshot'
import type { LastAction } from '../state'
import { formatAgeIn, formatClock, formatTokensIn, dayOf, monthOf, timeOf, secondsOf } from './format'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const UNITS = { day: 'd', hour: 'h', minute: 'min' }

const formatDate = (iso: string): string => `${MONTHS[monthOf(iso)] ?? ''} ${dayOf(iso)}`
const formatDateTime = (iso: string): string => `${formatDate(iso)} ${timeOf(iso)}`
const formatAge = (fromIso: string, nowMs: number): string => formatAgeIn(UNITS, fromIso, nowMs)
const formatTokens = (n: number): string => formatTokensIn('.', n)

/** Captions of the canonical answers (the_nod/vocab.py); any other value is a free option and stays as is. */
const ANSWERS: Record<string, string> = {
  done: 'Done', postpone: 'Postpone', yes: 'Yes', no: 'No', wait: 'Wait', accept: 'Accept', return: 'Return',
  rerun: 'Rerun', backlog: 'To backlog', restart: 'Restart',
}
const RESULTS: Record<string, string> = { solved: 'solved', unsolved: 'not solved', unverified: 'not verified' }
const SUGGESTIONS: Record<string, string> = { proposed: 'proposed', applied: 'applied' }
const RESULT_WORD: Record<LastAction['result'], string> = { running: 'running', ok: 'ok', error: 'error', ignored: 'ignored' }

type Counted = { runs: number; steps_done: number; accepted: number; tokens: number }
type Queued = { id: string; title: string; brief: string | null }
type Verdict = { card: string | null; card_title: string | null; acceptance?: { evidence: string } | null }

const registryTail = (source: string | null, why: string): string =>
  'in the engine registry: ' + (source === null ? 'no — ' + why : `yes (${source})`)

export const EN = {
  // Zones and their empty lines.
  zoneWaiting: 'Waiting for you',
  zoneRunning: 'In a run',
  zoneSince: 'While you were away',
  zoneBacklog: 'Backlog',
  zoneReview: 'Weekly review',
  emptyWaiting: 'No decisions',
  emptyRunning: 'Nothing running',
  emptySince: 'Quiet',
  emptyBacklog: 'The backlog is empty',
  emptyReview: 'No review yet: nod review week',
  zoneTitle: (name: string, count: number | string): string => `${name} · ${count}`,

  // Header, notices and the loading line.
  loading: 'Nod: reading state…',
  nodMissing: 'nod not found: Python 3.13 is needed in PATH; your own command — /config, field nod.core',
  legacyFound: 'found .sprintboot/ from an older version: /nod migrate',
  refresh: 'Refresh',
  staleLine: (since: string): string =>
    `State not fresh since ${formatDateTime(since)}: writes are off, run git pull first`,
  headerLine: (project: string, host: string, age: string): string => `${project} · ${host} · updated ${age} ago`,
  /** Header hint while the pane does not hold the keyboard; the status once it does (focus.ts). */
  focusHint: 'the first click on the pane gives it focus, the second one acts',
  focusGained: (): string => 'Nod: the pane has focus — a button press will work',
  /** Header tail: when and for which time this instance drew the pane. */
  renderedTail: (at: number, n: number): string => ` · drawn ${formatClock(at)} · #${n}`,

  // Dates, ages and counts.
  formatDate,
  formatDateTime,
  formatAge,
  formatTokens,
  sinceCount: (iso: string): string => 'since ' + formatDate(iso),
  more: (n: number): string => n + ' more',

  // Finding the core (nod.ts, register.tsx).
  nodNotFound: 'nod not found: Python 3.13 is needed (python.org), python, python3 or py in PATH; restart the session after installing',
  probeNoStart: 'does not start',
  probeExit: (code: number, line: string): string => (line === '' ? `code ${code}` : `code ${code}: ${line}`),
  probeLine: (argv: readonly string[], why: string): string => '  ' + argv.join(' ') + ' — ' + why,
  nodLine: (prefix: readonly string[]): string => 'nod: ' + prefix.join(' '),
  nodCheckingLine: 'nod: checking…',
  nodMissingLog: 'nod not found — Python 3.13 is needed (python.org) or your own command in /config, field nod.core',

  // Answers of /nod and its subcommands (register.tsx, subcommand.ts).
  commandDescription: 'Open the Nod pane',
  openHint: 'Nod: /nod opens the pane',
  subUnknown: 'unknown subcommand: /nod, /nod init, /nod migrate, /nod doctor, /nod install',
  subNoNod: 'core not found — the subcommand did not run',
  subChecking: 'the core is still being checked — try again in a few seconds',
  subFailed: (sub: string, why: string): string => `nod ${sub} failed: ${why}`,
  initDone: (dir: string): string => `state created: ${dir}; pane opened`,
  migrateDone: (dir: string): string => `state migrated: ${dir}; pane opened`,
  noState: (cwd: string): string => `Nod: no state — no .nod/state.json in ${cwd} or above`,
  paneFailed: (reason: string): string => 'Nod: the pane did not open — ' + reason,
  paneNotPlaced: (reason: string, dir: string): string => 'Nod: the pane is not placed — ' + reason + ' · ' + dir,
  paneOpened: (dir: string): string => 'Nod: pane opened · ' + dir,

  // Errors of reading the snapshot (refresh.ts, snapshot.ts).
  missingHint: 'no file — run nod status',
  nodStatusPrefix: 'nod status: ',
  notJson: (reason: string): string => 'not JSON: ' + reason,
  notObject: 'expected an object',
  unknownSchema: (schema: string): string => `schema ${schema}, the mod knows 1`,
  noField: (field: string): string => 'no field ' + field,
  notArray: (field: string): string => 'field ' + field + ' is not an array',
  notNumber: (field: string): string => 'field ' + field + ' is not a number',

  // Running nod (nod.ts) and submitting a prompt (actions.ts).
  exitCodeLine: (code: number): string => `exit code ${code}`,
  cannotStart: (program: string): string => `could not start ${program}`,
  promptDropped: (reason: string): string => 'prompt not accepted — ' + reason,
  /** Error prefix of the core's stderr in this language and of a timed line in the debug log. */
  errorPrefix: 'error: ',

  // Debug log lines (log.ts, nod.ts, actions.ts, register.tsx): timings to take a slow button apart.
  logLine: (text: string): string => 'nod: ' + text,
  timedLine: (label: string, ms: number, tail: string): string => `${label} — ${ms} ms` + (tail === '' ? '' : ', ' + tail),
  exitTail: (code: number): string => `code ${code}`,
  slowRender: (ms: number): string => `render — ${ms} ms`,
  renderAfterClick: (ms: number): string => `render after click — ${ms} ms`,
  busyShown: (ms: number): string => `“saving…” shown +${ms} ms`,
  sinceClick: (what: string, ms: number): string => `${what} +${ms} ms`,
  nodAnswerSpan: (ms: number): string => `nod answer ${ms} ms`,
  clickPending: 'pending',
  clickRead: 'reread',
  clickReleased: 'buttons back',
  clickFailed: 'not saved',
  reanchorLabel: (id: string): string => 're-anchor ' + id,
  clickLine: (id: string, parts: readonly string[]): string => `click ${id}: ` + parts.join(', '),

  // Decision cards (draw/waiting.tsx, draw/write-state.tsx).
  proposedSuffix: ' · proposed',
  /** Label of an owner-action above the question: "do it yourself", not a question and not "not saved". */
  needsAction: 'Action needed',
  busy: 'saving…',
  retry: 'Retry',
  notWritten: (message: string): string => 'not saved: ' + message,
  /** Caption of a canonical answer; an unknown value (a fork option) — as is. */
  answerLabel: (value: string): string => ANSWERS[value] ?? value,
  answerAll: 'Accept all proposed',
  busyAll: (n: number, m: number): string => `saving ${n} of ${m}…`,
  free: 'Your own answer',
  freePlaceholder: 'up to 20 words',
  freeSubmit: 'save',
  cancel: 'Cancel',

  // Footer (draw/footer.tsx).
  toChat: 'Goes to the chat',
  send: 'Send',
  clear: 'Clear',

  // Backlog and "Next step" (draw/backlog.tsx).
  nextStep: 'Next step',
  briefReady: 'brief ready',
  takeFirst: 'Take the first card',
  showBrief: 'Show the brief',
  showBacklog: 'Show the backlog',
  ownPain: 'Name another pain',
  sortOut: 'Sort out what hurts',
  emptyPainLine: 'The backlog is empty. Ten minutes of brainstorming will give you the first cards.',
  promptPain: 'Sort out what hurts: brainstorm with me for 10 minutes about what gets in the way in the project, '
    + 'and add cards with nod card add.',
  nextLine: (title: string): string => 'No decisions. Top of the backlog: “' + title + '”',
  promptTake: (c: Queued, stateDir: string): string => {
    const sep = sepOf(stateDir)
    const tail = c.brief
      ? 'open the brief ' + c.brief + ' and start a run of the first open step with nod run start ' + c.id
      : 'write the brief, and put your questions to me with nod decision ask --kind fork --card ' + c.id

    return 'Start work on card ' + c.id + ' “' + c.title + '”: read its file in '
      + stateDir + sep + 'cards' + sep + ', ' + tail + '.'
  },
  promptBacklog: (stateDir: string): string =>
    'Show the whole project backlog: run nod --root ' + stateDir + ' status --peek and list the cards in order with their statuses.',
  promptBrief: (c: Queued): string =>
    'Open the brief ' + c.brief + ' and sum up its “Decisions” and “How we check” sections in ten lines.',

  // "In a run" and "While you were away" (draw/running.tsx, draw/since.tsx).
  step: 'step',
  noStep: 'run not started',
  contracts: 'contracts',
  runningFor: 'running',
  lockLine: (host: string, at: string): string => `work in progress on ${host} since ${formatDateTime(at)}`,
  countersLine: (s: Counted): string =>
    `runs ${s.runs} · steps ${s.steps_done} · accepted ${s.accepted} · tokens ${formatTokens(s.tokens)}`,

  // "Weekly review" (draw/review.tsx).
  applySuggestions: 'Apply the suggestions',
  noSuggestions: 'No suggestions',
  reviewLine: (r: Review): string =>
    `runs ${r.runs} · steps ${r.steps_done} · stops ${r.stops} · accepted ${r.accepted} · tokens ${formatTokens(r.tokens)} · ${r.minutes} min`,
  reviewPeriod: (r: Review): string => `${formatDate(r.since)} — ${formatDate(r.until)}`,
  suggestionLine: (s: ReviewSuggestion): string => `${s.n}. ${s.text}`,
  /** Caption of a suggestion status (proposed, applied); an unknown one — as is. */
  suggestionStatus: (status: string): string => SUGGESTIONS[status] ?? status,
  /** Prompt "Apply the suggestions": the numbers are only the items with status proposed. */
  promptApply: (r: Review, stateDir: string): string => {
    const sep = sepOf(stateDir)
    const numbers = r.suggestions.filter(s => s.status === 'proposed').map(s => s.n).join(', ')

    return `Apply the suggestions of weekly review ${r.week}: open ${stateDir}${sep}reviews${sep}${r.week}.md, `
      + `section “What to improve”, items ${numbers}. Make each one a change to the harness rules: the project's harness.toml, `
      + 'the adapter prompts in the Nod repository (the_nod/prompts) or the project\'s CLAUDE.md. '
      + `Mark an applied item: nod --root ${stateDir} review mark ${r.week} <number> --applied. `
      + 'What cannot be applied — explain it and leave the status as is.'
  },

  // Acceptance card (draw/acceptance.tsx).
  acceptor: 'Acceptance',
  /** Caption of an acceptance result (solved, unsolved, unverified); an unknown one — as is. */
  resultLabel: (result: string): string => RESULTS[result] ?? result,
  acceptClose: 'Confirm — close',
  returnLabel: 'Not right — return',
  acceptAsIs: 'Accept as is',
  giveWay: 'Suggest a way to check',
  whatWrong: 'What is wrong',
  returnSubmit: 'return',
  moreLabel: 'More',
  lessLabel: 'Less',
  see: 'see',
  report: 'Acceptance report',
  framesTitle: (n: number): string => `Look at the frames · ${n}`,
  stepsTitle: (n: number): string => `By hand · ${n} ${n === 1 ? 'step' : 'steps'}`,
  promptVerify: (d: Verdict): string =>
    'The acceptance of card ' + d.card + ' “' + d.card_title + '” is not verified: ' + (d.acceptance?.evidence ?? '')
    + '. Suggest how to check it without what is missing, and describe the steps.',

  // Self-diagnosis (actions.ts, report.ts, draw/footer.tsx): the status line and the footer's last action.
  pressedStatus: (label: string): string => `Nod: pressed “${label}”…`,
  pressedLog: (label: string, ms: number): string => `Nod: pressed “${label}” · ${formatClock(ms)}`,
  pressedToast: (label: string): string => `Nod: pressed “${label}”`,
  writingStatus: (id: string): string => `Nod: saving ${id}…`,
  wroteStatus: (target: string, ms: number): string => `Nod: saved ${target} · ${ms} ms`,
  failedStatus: (target: string, reason: string): string => `Nod: not saved ${target} — ${reason}`,
  doneStatus: (what: string, ms: number): string => `Nod: ${what} — done · ${ms} ms`,
  errorStatus: (what: string, reason: string): string => `Nod: ${what} — error: ${reason}`,
  ignoredStatus: (reason: string): string => 'Nod: ignored — ' + reason,
  waitCoreStatus: 'Nod: waiting for the snapshot rebuild…',
  statusLine: (text: string): string => 'Nod: ' + text,
  whatAnswer: (id: string): string => 'answer ' + id,
  whatRetry: (id?: string): string => (id === undefined ? 'retry' : 'retry ' + id),
  whatAll: 'answer all',
  whatSend: 'send to chat',
  whatRefresh: 'snapshot refresh',
  allTarget: (n: number): string => `all (${n})`,
  busyWith: (id: string, since: number): string => `saving ${id} since ${formatClock(since)}`,
  takeoverLine: (token: string): string =>
    `Nod: the pane is recorded for another instance: ${token} — drawing it myself, keep one load`,
  reclaimLine: (token: string): string =>
    `Nod: the pane is recorded for the previous load of this folder: ${token} — drawing it as mine`,
  /** Tail of a reason when the click path takes the session-start value instead of a silent atom. */
  fallbackNote: 'taking the value from session start',
  rereadLabel: 'reread the snapshot',
  nodChecking: 'nod is still being checked',
  noStateDir: 'state folder not found',
  sendingNow: 'sending in progress',
  nothingToRetry: 'nothing to retry',
  noSnapshot: 'no snapshot',
  notFresh: 'snapshot not fresh',
  emptyDraft: 'the draft is empty',
  stuckReset: (sec: number): string => `reset a stuck lock (${sec} s)`,
  coreTimeout: (sec: number): string => `the snapshot rebuild did not finish in ${sec} s, saving`,
  overtakenLine: (what: string, tail: string): string =>
    `${what}: the lock was taken as stuck, result “${tail}” not shown`,
  panelStuck: (label: string, error: string): string => `pane state does not respond (${label}: ${error})`,
  goingOn: (text: string): string => text + ' — going on',
  /** Timeout of an atom write: "timeout 2 s". */
  timeoutText: (ms: number): string => `timeout ${secondsOf(ms)} s`,
  lastPressLine: (text: string | null): string => 'last press: ' + (text ?? 'no presses yet'),
  /** "last action: answer d-pcfd · 843 ms · ok"; the detail of an error or a skip goes after a colon. */
  lastActionLine: (a: LastAction): string => {
    const word = RESULT_WORD[a.result]
    const tail = a.detail === '' ? word : a.result === 'ok' ? word + ' · ' + a.detail : word + ': ' + a.detail

    return 'last action: ' + [a.what, ...(a.ms === null ? [] : [`${a.ms} ms`]), tail].join(' · ')
  },

  // Loading the mod and resetting its state (register.tsx, session.start).
  resetWhat: 'state reset',
  resetFailed: (key: string, error: string): string => `${key} (${error})`,
  /** Load line; `fact` is the registration fact of /nod (registryLine). */
  loadedLine: (root: string, id: string, failed: readonly string[], fact: string): string =>
    `Nod: mod loaded from ${root} · instance ${id} · state reset`
    + (failed.length === 0 ? '' : ' incompletely: ' + failed.join(', '))
    + ' · ' + fact,

  // Registering /nod against the engine registry (command.ts).
  listMissing: 'the command is not in the list',
  listFailed: (error: string): string => 'the command list did not answer: ' + error,
  listMalformed: 'the answer is not a list',
  registerTimeout: 'registration did not answer in 2 s',
  noAttempt: '/nod: no registration in this load',
  /** `source` — where the command is listed from (null — it is not there), `why` — the reason for "no". */
  registryTail,
  registryLine: (error: string | null, source: string | null, why: string): string =>
    (error === null ? '/nod registered' : source === null ? '/nod not registered' : `/nod not registered (${error})`)
    + ', ' + registryTail(source, why),
  afterStart: 'after session start',
  afterTurn: 'after the first answer',
  retryLine: (when: string, fact: string): string => `Nod: registration retry ${when} — ${fact}`,

  // Diagnostics of /nod (diag.ts).
  selfLine: (id: string, root: string): string => `instance ${id} · root ${root}`,
  ownerMine: (): string => 'pane owner: this instance',
  ownerForeign: (token: string): string => 'pane owner: another one — ' + token,
  ownerUnset: (): string => 'pane owner: not recorded',
  ownerSilent: (error: string): string => `pane owner: state did not answer (${error})`,
  pendingLine: (pending: string | null): string => 'pending: ' + (pending ?? '—'),
  noActionLine: 'last action: —',
  rendersLine: (n: number, at: number | null): string => `renders: ${n}` + (at === null ? '' : ` · last ${formatClock(at)}`),

  // Double load of the mod (owner.ts): the owner's line in the pane and in /nod.
  doubleLoadLine: (a: string, b: string): string =>
    `the mod is loaded twice: ${a} and ${b} — keep one (env CLAUDE_CODE_PLUGIN_DIRS or dev-mods)`,
}

/** Shape of a dictionary: the English one. */
export type Texts = typeof EN
