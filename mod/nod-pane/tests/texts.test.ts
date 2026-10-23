// The two dictionaries: English is the default and carries no Cyrillic letter; Russian has the same keys and shape.
import { test, expect } from 'claude-code/testing'
import { EN, RU, langOf, textsFor } from '../hooks/texts/index'
import type { Texts } from '../hooks/texts/index'
import type { Waiting } from '../hooks/snapshot'
import { REVIEW, STATE_FULL } from './fixtures'

const CYRILLIC = /[\u0400-\u04FF]/
const ISO = '2026-10-20T08:00:00'
const NOW = Date.parse('2026-10-20T10:12:00')
const QUEUED = { id: 'c-2001', title: 'Show the history of check-ins', brief: 'docs/briefs/history.md' }
const VERDICT = STATE_FULL.waiting[2] as Waiting
const SUGGESTION = REVIEW.suggestions[0] as (typeof REVIEW.suggestions)[number]
const action = (result: 'running' | 'ok' | 'error' | 'ignored', detail: string, ms: number | null) =>
  ({ what: 'answer d-fork', at: 0, ms, result, detail })

type Fn = (...args: never[]) => string

/** Sample calls of every function of a dictionary: each one, run on each sample, gives a line to check. */
const SAMPLES: Record<string, (t: Texts) => string[]> = {
  zoneTitle: t => [t.zoneTitle('Backlog', 3), t.zoneTitle('Weekly review', '2026-43')],
  staleLine: t => [t.staleLine(ISO)],
  headerLine: t => [t.headerLine('tidepool', 'laptop', '12 min')],
  focusGained: t => [t.focusGained()],
  renderedTail: t => [t.renderedTail(NOW, 7)],
  formatDate: t => ['2026-01-05', '2026-05-01', '2026-12-31'].map(d => t.formatDate(d + 'T00:00:00')),
  formatDateTime: t => [t.formatDateTime(ISO)],
  formatAge: t => [t.formatAge('2026-10-20T10:00:00', NOW), t.formatAge('2026-10-20T09:00:00', NOW),
    t.formatAge('2026-10-20T08:12:00', NOW), t.formatAge('2026-10-17T10:00:00', NOW)],
  formatTokens: t => [t.formatTokens(25000000), t.formatTokens(812000), t.formatTokens(730)],
  sinceCount: t => [t.sinceCount(ISO)],
  more: t => [t.more(39)],
  probeExit: t => [t.probeExit(9009, 'Python was not found'), t.probeExit(1, '')],
  probeLine: t => [t.probeLine(['nod', '--help'], t.probeNoStart)],
  nodLine: t => [t.nodLine(['python', '-P', 'main.py'])],
  subFailed: t => [t.subFailed('migrate', 'branch main is protected')],
  initDone: t => [t.initDone('D:\\x\\proj\\.nod')],
  migrateDone: t => [t.migrateDone('D:\\x\\proj\\.nod')],
  noState: t => [t.noState('D:\\x\\proj')],
  paneFailed: t => [t.paneFailed('no surface')],
  paneNotPlaced: t => [t.paneNotPlaced('width 90', 'D:\\x\\proj\\.nod')],
  paneOpened: t => [t.paneOpened('D:\\x\\proj\\.nod')],
  notJson: t => [t.notJson('Unexpected end of input')],
  unknownSchema: t => [t.unknownSchema('2')],
  noField: t => [t.noField('since.from')],
  notArray: t => [t.notArray('waiting')],
  notNumber: t => [t.notNumber('backlog.total')],
  exitCodeLine: t => [t.exitCodeLine(3)],
  cannotStart: t => [t.cannotStart('nod')],
  promptDropped: t => [t.promptDropped('the queue is closed')],
  logLine: t => [t.logLine('text')],
  timedLine: t => [t.timedLine('nod status', 12, ''), t.timedLine('nod status', 12, t.exitTail(0))],
  exitTail: t => [t.exitTail(0)],
  slowRender: t => [t.slowRender(201)],
  renderAfterClick: t => [t.renderAfterClick(5)],
  busyShown: t => [t.busyShown(5)],
  sinceClick: t => [t.sinceClick(t.clickPending, 3)],
  nodAnswerSpan: t => [t.nodAnswerSpan(40)],
  reanchorLabel: t => [t.reanchorLabel('d-fork')],
  clickLine: t => [t.clickLine('d-fork', [t.clickFailed, t.clickRead, t.clickReleased])],
  notWritten: t => [t.notWritten('state not fresh')],
  answerLabel: t => ['done', 'postpone', 'yes', 'no', 'wait', 'accept', 'return', 'rerun', 'backlog', 'restart', 'ISO']
    .map(v => t.answerLabel(v)),
  busyAll: t => [t.busyAll(1, 3)],
  nextLine: t => [t.nextLine(QUEUED.title)],
  promptTake: t => [t.promptTake(QUEUED, 'D:\\x\\proj\\.nod'), t.promptTake({ ...QUEUED, brief: null }, '/home/x/proj/.nod')],
  promptBacklog: t => [t.promptBacklog('D:\\x\\proj\\.nod')],
  promptBrief: t => [t.promptBrief(QUEUED)],
  lockLine: t => [t.lockLine('desktop', ISO)],
  countersLine: t => [t.countersLine(STATE_FULL.since)],
  reviewLine: t => [t.reviewLine(REVIEW)],
  reviewPeriod: t => [t.reviewPeriod(REVIEW)],
  suggestionLine: t => [t.suggestionLine(SUGGESTION)],
  suggestionStatus: t => ['proposed', 'applied'].map(s => t.suggestionStatus(s)),
  promptApply: t => [t.promptApply(REVIEW, 'D:\\x\\proj\\.nod')],
  resultLabel: t => ['solved', 'unsolved', 'unverified'].map(r => t.resultLabel(r)),
  framesTitle: t => [t.framesTitle(6)],
  stepsTitle: t => [1, 2, 5, 11, 21].map(n => t.stepsTitle(n)),
  promptVerify: t => [t.promptVerify(VERDICT)],
  pressedStatus: t => [t.pressedStatus('ISO')],
  pressedLog: t => [t.pressedLog('ISO', NOW)],
  pressedToast: t => [t.pressedToast('ISO')],
  writingStatus: t => [t.writingStatus('d-fork')],
  wroteStatus: t => [t.wroteStatus(t.allTarget(3), 40)],
  failedStatus: t => [t.failedStatus('d-fork', 'state not fresh')],
  doneStatus: t => [t.doneStatus(t.whatSend, 40)],
  errorStatus: t => [t.errorStatus(t.whatRefresh, 'network')],
  ignoredStatus: t => [t.ignoredStatus(t.sendingNow)],
  statusLine: t => [t.statusLine('text')],
  whatAnswer: t => [t.whatAnswer('d-fork')],
  whatRetry: t => [t.whatRetry(), t.whatRetry('d-fork')],
  allTarget: t => [t.allTarget(3)],
  busyWith: t => [t.busyWith('d-fork', NOW)],
  takeoverLine: t => [t.takeoverLine('zzz@D:\\mod')],
  reclaimLine: t => [t.reclaimLine('old@D:\\mod')],
  stuckReset: t => [t.stuckReset(210)],
  coreTimeout: t => [t.coreTimeout(70)],
  overtakenLine: t => [t.overtakenLine(t.whatAll, 'ok')],
  panelStuck: t => [t.panelStuck('snapshot', t.timeoutText(2000))],
  goingOn: t => [t.goingOn('text')],
  timeoutText: t => [t.timeoutText(2000)],
  lastPressLine: t => [t.lastPressLine(null), t.lastPressLine('Nod: saved d-fork · 40 ms')],
  lastActionLine: t => [t.lastActionLine(action('ok', '', 843)), t.lastActionLine(action('error', 'could not start nod', 12)),
    t.lastActionLine(action('ignored', 'saving d-yyyy', null)), t.lastActionLine(action('running', '', null))],
  resetFailed: t => [t.resetFailed('freeFor', 'forbidden')],
  loadedLine: t => [t.loadedLine('D:\\mod', 'abc', [], 'fact'), t.loadedLine('D:\\mod', 'abc', ['freeFor (forbidden)'], 'fact')],
  listFailed: t => [t.listFailed('timeout')],
  registryTail: t => [t.registryTail(null, t.listMissing), t.registryTail('plugin nod', '')],
  registryLine: t => [t.registryLine(null, 'plugin nod', ''), t.registryLine('forbidden', null, 'forbidden'),
    t.registryLine('forbidden', 'plugin nod', '')],
  retryLine: t => [t.retryLine(t.afterStart, 'fact'), t.retryLine(t.afterTurn, 'fact')],
  selfLine: t => [t.selfLine('abc', 'D:\\mod')],
  ownerMine: t => [t.ownerMine()],
  ownerForeign: t => [t.ownerForeign('zzz@D:\\mod')],
  ownerUnset: t => [t.ownerUnset()],
  ownerSilent: t => [t.ownerSilent('timeout')],
  pendingLine: t => [t.pendingLine(null), t.pendingLine('d-fork')],
  rendersLine: t => [t.rendersLine(3, null), t.rendersLine(3, NOW)],
  doubleLoadLine: t => [t.doubleLoadLine('D:\\a', 'D:\\b')],
}

/** Every line of a dictionary: its strings and its functions on the sample arguments. */
function linesOf(t: Texts): string[] {
  return Object.entries(t).flatMap(([key, value]) => {
    if (typeof value === 'string') return [value]
    const sample = SAMPLES[key]
    if (sample === undefined) throw new Error('no sample call for ' + key)

    return sample(t)
  })
}

test('english dictionary has no cyrillic', () => {
  const found = linesOf(EN).filter(line => CYRILLIC.test(line))
  expect(found).toEqual([])
})

test('every function of a dictionary has a sample call and gives text', () => {
  for (const t of [EN, RU]) {
    for (const line of linesOf(t)) expect(typeof line).toBe('string')
  }
  expect(Object.keys(SAMPLES).filter(key => typeof (EN as Record<string, unknown>)[key] !== 'function')).toEqual([])
})

test('the Russian dictionary has the same keys, kinds and arities as the English one', () => {
  expect(Object.keys(RU).sort()).toEqual(Object.keys(EN).sort())
  for (const [key, value] of Object.entries(EN)) {
    const other = (RU as Record<string, unknown>)[key]
    expect([key, typeof other]).toEqual([key, typeof value])
    if (typeof value === 'function') expect([key, (other as Fn).length]).toEqual([key, (value as Fn).length])
  }
})

test('the Russian dictionary is Russian: zone names and captions in Cyrillic', () => {
  expect([RU.zoneWaiting, RU.zoneBacklog, RU.needsAction, RU.answerLabel('postpone')].every(s => CYRILLIC.test(s))).toBe(true)
})

test('langOf: the snapshot lang field; missing or unknown — English', () => {
  expect(langOf({ lang: 'ru' })).toBe('ru')
  expect(langOf({ lang: 'en' })).toBe('en')
  expect(langOf({ ...STATE_FULL })).toBe('en')
  expect(langOf({ lang: 'de' })).toBe('en')
  expect(langOf({ lang: 'RU' })).toBe('en')
  expect(langOf(null)).toBe('en')
  expect(langOf('ru')).toBe('en')
  expect(textsFor('ru')).toBe(RU)
  expect(textsFor('en')).toBe(EN)
})

test('the legacy hint names /nod migrate in both languages', () => {
  expect(EN.legacyFound).toMatch(/\/ from an older version: \/nod migrate$/)
  expect(RU.legacyFound).toMatch(/\/nod migrate$/)
  expect(EN.subUnknown).toBe('unknown subcommand: /nod, /nod init, /nod migrate, /nod doctor, /nod install')
  expect(RU.subUnknown).toContain('/nod, /nod init, /nod migrate, /nod doctor, /nod install')
})
