// Russian texts of the pane and of /nod: the snapshot says `"lang": "ru"`. Same keys as the English dictionary.
import { sepOf } from '../find'
import type { Review, ReviewSuggestion } from '../snapshot'
import type { LastAction } from '../state'
import type { Texts } from './en'
import { formatAgeIn, formatClock, formatTokensIn, dayOf, monthOf, timeOf, secondsOf } from './format'

const MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
const UNITS = { day: 'дн', hour: 'ч', minute: 'мин' }

const formatDate = (iso: string): string => `${dayOf(iso)} ${MONTHS[monthOf(iso)] ?? ''}`
const formatDateTime = (iso: string): string => `${formatDate(iso)} ${timeOf(iso)}`
const formatAge = (fromIso: string, nowMs: number): string => formatAgeIn(UNITS, fromIso, nowMs)
const formatTokens = (n: number): string => formatTokensIn(',', n)

const ANSWERS: Record<string, string> = {
  done: 'Сделано', postpone: 'Отложить', yes: 'Да', no: 'Нет', wait: 'Подождать', accept: 'Принять', return: 'Вернуть',
  rerun: 'Перезапустить', backlog: 'В бэклог', restart: 'Начать заново',
}
const RESULTS: Record<string, string> = { solved: 'решилась', unsolved: 'не решилась', unverified: 'не проверено' }
const SUGGESTIONS: Record<string, string> = { proposed: 'предлагается', applied: 'внесено' }
const RESULT_WORD: Record<LastAction['result'], string> = { running: 'идёт', ok: 'ok', error: 'ошибка', ignored: 'проигнорировано' }

type Counted = { runs: number; steps_done: number; accepted: number; tokens: number }
type Queued = { id: string; title: string; brief: string | null }
type Verdict = { card: string | null; card_title: string | null; acceptance?: { evidence: string } | null }

const registryTail = (source: string | null, why: string): string =>
  'в реестре движка: ' + (source === null ? 'нет — ' + why : `да (${source})`)

function stepsWord(n: number): string {
  const tail = n % 100
  const last = n % 10
  if (tail >= 11 && tail <= 14) return 'шагов'
  if (last === 1) return 'шаг'

  return last >= 2 && last <= 4 ? 'шага' : 'шагов'
}

export const RU: Texts = {
  zoneWaiting: 'Ждёт тебя',
  zoneRunning: 'В ране',
  zoneSince: 'Пока тебя не было',
  zoneBacklog: 'Бэклог',
  zoneReview: 'Обзор недели',
  emptyWaiting: 'Решений нет',
  emptyRunning: 'Пусто',
  emptySince: 'Тихо',
  emptyBacklog: 'Бэклог пуст',
  emptyReview: 'Обзора ещё нет: nod review week',
  zoneTitle: (name, count) => `${name} · ${count}`,

  loading: 'Nod: читаю состояние…',
  nodMissing: 'nod не найден: нужен Python 3.13 в PATH; своя команда — /config, поле nod.core',
  legacyFound: 'найдена .sprintboot/ от старой версии: /nod migrate',
  refresh: 'Обновить',
  staleLine: since => `Состояние не свежее с ${formatDateTime(since)}: записи отключены, сначала git pull`,
  headerLine: (project, host, age) => `${project} · ${host} · обновлено ${age} назад`,
  focusHint: 'первый клик по панели даёт ей фокус, второй — действие',
  focusGained: () => 'Nod: панель в фокусе — нажатие кнопки сработает',
  renderedTail: (at, n) => ` · отрисовано ${formatClock(at)} · #${n}`,

  formatDate,
  formatDateTime,
  formatAge,
  formatTokens,
  sinceCount: iso => 'с ' + formatDate(iso),
  more: n => 'ещё ' + n,

  nodNotFound: 'nod не найден: нужен Python 3.13 (python.org), python, python3 или py в PATH; после установки перезапусти сессию',
  probeNoStart: 'не запускается',
  probeExit: (code, line) => (line === '' ? `код ${code}` : `код ${code}: ${line}`),
  probeLine: (argv, why) => '  ' + argv.join(' ') + ' — ' + why,
  nodLine: prefix => 'nod: ' + prefix.join(' '),
  nodCheckingLine: 'nod: проверяю…',
  nodMissingLog: 'nod не найден — нужен Python 3.13 (python.org) или своя команда в /config, поле nod.core',

  commandDescription: 'Открыть панель Nod',
  openHint: 'Nod: /nod откроет панель',
  subUnknown: 'не знаю такой подкоманды: /nod, /nod init, /nod migrate, /nod doctor, /nod install',
  subNoNod: 'ядро не найдено — подкоманда не выполнена',
  subChecking: 'ядро ещё проверяется — повтори через несколько секунд',
  subFailed: (sub, why) => `nod ${sub} не прошёл: ${why}`,
  initDone: dir => `состояние создано: ${dir}; панель открыта`,
  migrateDone: dir => `состояние перенесено: ${dir}; панель открыта`,
  noState: cwd => `Nod: состояния нет — в ${cwd} и выше нет .nod/state.json`,
  paneFailed: reason => 'Nod: панель не открылась — ' + reason,
  paneNotPlaced: (reason, dir) => 'Nod: панель не села — ' + reason + ' · ' + dir,
  paneOpened: dir => 'Nod: панель открыта · ' + dir,

  missingHint: 'файла нет — выполни nod status',
  nodStatusPrefix: 'nod status: ',
  notJson: reason => 'не JSON: ' + reason,
  notObject: 'ждал объект',
  unknownSchema: schema => `schema ${schema}, мод знает 1`,
  noField: field => 'нет поля ' + field,
  notArray: field => 'поле ' + field + ' не массив',
  notNumber: field => 'поле ' + field + ' не число',

  exitCodeLine: code => `код выхода ${code}`,
  cannotStart: program => `не удалось запустить ${program}`,
  promptDropped: reason => 'промпт не принят — ' + reason,
  errorPrefix: 'ошибка: ',

  logLine: text => 'nod: ' + text,
  timedLine: (label, ms, tail) => `${label} — ${ms} мс` + (tail === '' ? '' : ', ' + tail),
  exitTail: code => `код ${code}`,
  slowRender: ms => `render — ${ms} мс`,
  renderAfterClick: ms => `render после клика — ${ms} мс`,
  busyShown: ms => `«записываю…» показано +${ms} мс`,
  sinceClick: (what, ms) => `${what} +${ms} мс`,
  nodAnswerSpan: ms => `nod answer ${ms} мс`,
  clickPending: 'pending',
  clickRead: 'перечитан',
  clickReleased: 'кнопки возвращены',
  clickFailed: 'не записано',
  reanchorLabel: id => 'ре-анкор ' + id,
  clickLine: (id, parts) => `клик ${id}: ` + parts.join(', '),

  proposedSuffix: ' · предложено',
  needsAction: 'Нужно действие',
  busy: 'записываю…',
  retry: 'Повторить',
  notWritten: message => 'не записано: ' + message,
  answerLabel: value => ANSWERS[value] ?? value,
  answerAll: 'Согласен со всеми предложенными',
  busyAll: (n, m) => `записываю ${n} из ${m}…`,
  free: 'Свой ответ',
  freePlaceholder: 'до 20 слов',
  freeSubmit: 'записать',
  cancel: 'Отмена',

  toChat: 'В чат уйдёт',
  send: 'Отправить',
  clear: 'Очистить',

  nextStep: 'Следующий шаг',
  briefReady: 'бриф готов',
  takeFirst: 'Взять первую',
  showBrief: 'Показать бриф',
  showBacklog: 'Показать бэклог',
  ownPain: 'Своя боль',
  sortOut: 'Разобрать, что болит',
  emptyPainLine: 'Бэклог пуст. Десять минут брейншторма дадут первые карточки.',
  promptPain: 'Разобрать, что болит: проведи со мной брейншторм на 10 минут о том, что мешает в проекте, '
    + 'и заведи карточки командой nod card add.',
  nextLine: title => 'Решений нет. Верх бэклога: «' + title + '»',
  promptTake: (c: Queued, stateDir) => {
    const sep = sepOf(stateDir)
    const tail = c.brief
      ? 'открой бриф ' + c.brief + ' и начни ран первого незакрытого шага командой nod run start ' + c.id
      : 'напиши бриф, а вопросы ко мне оформи командой nod decision ask --kind fork --card ' + c.id

    return 'Начни работу по карточке ' + c.id + ' «' + c.title + '»: прочитай её файл в '
      + stateDir + sep + 'cards' + sep + ', ' + tail + '.'
  },
  promptBacklog: stateDir =>
    'Покажи бэклог проекта целиком: выполни nod --root ' + stateDir + ' status --peek и перечисли карточки по порядку с их статусами.',
  promptBrief: (c: Queued) =>
    'Открой бриф ' + c.brief + ' и перескажи разделы «Решения» и «Как проверим» в десяти строках.',

  step: 'шаг',
  noStep: 'ран не начат',
  contracts: 'контракты',
  runningFor: 'идёт',
  lockLine: (host, at) => `работа идёт на ${host} с ${formatDateTime(at)}`,
  countersLine: (s: Counted) =>
    `ранов ${s.runs} · шагов ${s.steps_done} · принято ${s.accepted} · токенов ${formatTokens(s.tokens)}`,

  applySuggestions: 'Внести предложения',
  noSuggestions: 'Предложений нет',
  reviewLine: (r: Review) =>
    `ранов ${r.runs} · шагов ${r.steps_done} · стопов ${r.stops} · принято ${r.accepted} · токенов ${formatTokens(r.tokens)} · ${r.minutes} мин`,
  reviewPeriod: (r: Review) => `${formatDate(r.since)} — ${formatDate(r.until)}`,
  suggestionLine: (s: ReviewSuggestion) => `${s.n}. ${s.text}`,
  suggestionStatus: status => SUGGESTIONS[status] ?? status,
  promptApply: (r: Review, stateDir) => {
    const sep = sepOf(stateDir)
    const numbers = r.suggestions.filter(s => s.status === 'proposed').map(s => s.n).join(', ')

    return `Внеси предложения обзора недели ${r.week}: открой ${stateDir}${sep}reviews${sep}${r.week}.md, `
      + `раздел «Что улучшить», пункты ${numbers}. По каждому внеси правку в правила харнеса: harness.toml проекта, `
      + 'промпты адаптера в репе Nod (the_nod/prompts) или CLAUDE.md проекта. '
      + `Внесённый пункт отметь: nod --root ${stateDir} review mark ${r.week} <номер> --applied. `
      + 'Что внести нельзя — объясни и статус не меняй.'
  },

  acceptor: 'Приёмщик',
  resultLabel: result => RESULTS[result] ?? result,
  acceptClose: 'Подтверждаю — закрыть',
  returnLabel: 'Не так — вернуть',
  acceptAsIs: 'Принять как есть',
  giveWay: 'Дать способ проверить',
  whatWrong: 'Что не так',
  returnSubmit: 'вернуть',
  moreLabel: 'Подробнее',
  lessLabel: 'Свернуть',
  see: 'увидеть',
  report: 'Отчёт приёмщика',
  framesTitle: n => `Взгляни на кадры · ${n}`,
  stepsTitle: n => `Руками · ${n} ${stepsWord(n)}`,
  promptVerify: (d: Verdict) =>
    'Приёмка карточки ' + d.card + ' «' + d.card_title + '» не проверена: ' + (d.acceptance?.evidence ?? '')
    + '. Предложи, как проверить её без того, чего нет, и опиши шаги.',

  pressedStatus: label => `Nod: нажато «${label}»…`,
  pressedLog: (label, ms) => `Nod: нажато «${label}» · ${formatClock(ms)}`,
  pressedToast: label => `Nod: нажато «${label}»`,
  writingStatus: id => `Nod: записываю ${id}…`,
  wroteStatus: (target, ms) => `Nod: записано ${target} · ${ms} мс`,
  failedStatus: (target, reason) => `Nod: не записано ${target} — ${reason}`,
  doneStatus: (what, ms) => `Nod: ${what} — готово · ${ms} мс`,
  errorStatus: (what, reason) => `Nod: ${what} — ошибка: ${reason}`,
  ignoredStatus: reason => 'Nod: проигнорировано — ' + reason,
  waitCoreStatus: 'Nod: жду пересборку снимка…',
  statusLine: text => 'Nod: ' + text,
  whatAnswer: id => 'ответ ' + id,
  whatRetry: id => (id === undefined ? 'повтор' : 'повтор ' + id),
  whatAll: 'ответ всем',
  whatSend: 'отправка в чат',
  whatRefresh: 'обновление снимка',
  allTarget: n => `всем (${n})`,
  busyWith: (id, since) => `идёт запись ${id} с ${formatClock(since)}`,
  takeoverLine: token => `Nod: панель записана за другим экземпляром: ${token} — рисую сам, оставь одну загрузку`,
  reclaimLine: token => `Nod: панель записана за прошлой загрузкой этой папки: ${token} — рисую как свою`,
  fallbackNote: 'беру значение старта сессии',
  rereadLabel: 'перечитать снимок',
  nodChecking: 'nod ещё проверяется',
  noStateDir: 'папка состояния не найдена',
  sendingNow: 'идёт отправка',
  nothingToRetry: 'нечего повторять',
  noSnapshot: 'снимка нет',
  notFresh: 'снимок не свежий',
  emptyDraft: 'черновик пуст',
  stuckReset: sec => `сброшен застрявший замок (${sec} с)`,
  coreTimeout: sec => `пересборка снимка не завершилась за ${sec} с, пишу`,
  overtakenLine: (what, tail) => `${what}: замок снят как застрявший, итог «${tail}» не показан`,
  panelStuck: (label, error) => `состояние панели не отвечает (${label}: ${error})`,
  goingOn: text => text + ' — продолжаю',
  timeoutText: ms => `таймаут ${secondsOf(ms)} с`,
  lastPressLine: text => 'последнее нажатие: ' + (text ?? 'нажатий не было'),
  lastActionLine: (a: LastAction) => {
    const word = RESULT_WORD[a.result]
    const tail = a.detail === '' ? word : a.result === 'ok' ? word + ' · ' + a.detail : word + ': ' + a.detail

    return 'последнее действие: ' + [a.what, ...(a.ms === null ? [] : [`${a.ms} мс`]), tail].join(' · ')
  },

  resetWhat: 'сброс состояния',
  resetFailed: (key, error) => `${key} (${error})`,
  loadedLine: (root, id, failed, fact) =>
    `Nod: мод загружен из ${root} · экземпляр ${id} · состояние сброшено`
    + (failed.length === 0 ? '' : ' не полностью: ' + failed.join(', '))
    + ' · ' + fact,

  listMissing: 'команды нет в списке',
  listFailed: error => 'список команд не ответил: ' + error,
  listMalformed: 'ответ не список',
  registerTimeout: 'регистрация не ответила за 2 с',
  noAttempt: '/nod: в этой загрузке регистрации не было',
  registryTail,
  registryLine: (error, source, why) =>
    (error === null ? '/nod зарегистрирована' : source === null ? '/nod не зарегистрирована' : `/nod не зарегистрирована (${error})`)
    + ', ' + registryTail(source, why),
  afterStart: 'после старта сессии',
  afterTurn: 'после первого ответа',
  retryLine: (when, fact) => `Nod: повтор регистрации ${when} — ${fact}`,

  selfLine: (id, root) => `экземпляр ${id} · корень ${root}`,
  ownerMine: () => 'владелец панели: этот экземпляр',
  ownerForeign: token => 'владелец панели: другой — ' + token,
  ownerUnset: () => 'владелец панели: не записан',
  ownerSilent: error => `владелец панели: состояние не ответило (${error})`,
  pendingLine: pending => 'pending: ' + (pending ?? '—'),
  noActionLine: 'последнее действие: —',
  rendersLine: (n, at) => `отрисовок: ${n}` + (at === null ? '' : ` · последняя ${formatClock(at)}`),

  doubleLoadLine: (a, b) => `мод загружен дважды: ${a} и ${b} — оставь один (env CLAUDE_CODE_PLUGIN_DIRS или dev-mods)`,
}
