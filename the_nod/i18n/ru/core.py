"""Russian messages of the core: the same keys and placeholders as `the_nod.i18n.en.core`.

Literal braces are doubled (`{{card}}`): every message goes through `str.format`.
"""

_HARNESS_TEMPLATE = """\
# Манифест драйвера: какой командой писать бриф, гнать шаг и принимать карточку.
# lang — язык интерфейса: en или ru; переменная окружения NOD_LANG сильнее.
lang = "{lang}"
# adapter — набор команд и промптов драйвера; сейчас есть только default.
adapter = "default"
driver_host = ""
# Пустая команда — команда адаптера по умолчанию.
# Подстановки в командах: {{card}} {{brief}} {{root}} {{answers}} {{result}} {{prompt}} {{step}} {{run}}.
# {{title}} и {{step_title}} — только в промптах: команда идёт в оболочку.
# Агент по умолчанию без git push, без переключения веток и без python -c; тесты проекта он запускает — это код, который он пишет сам. Шире — напиши свою команду с другим --allowedTools.
# Модель в командах по умолчанию (--model sonnet) — выбор владельца, меняй своей командой.
[commands]
brief = ""
run = ""
accept = ""

[git]
# false — Nod никогда не обращается к remote. true — pull перед каждой записью и push после неё: нужно, когда драйвер и ты работаете с двух машин.
push = false

# Что проекту нужно от машины: проверяет nod doctor, ставит nod install.
# [needs]
# python = "3.13"
# nod — пустая строка: не проверять, ядро приходит с плагином.
# nod = ""
# claude = "claude"
# jobs = ["driver"]
# skills = []
# agents = []
# rules = []
"""

MESSAGES = {
    # cli
    "cli.error": "ошибка: {message}",
    "cli.empty": "пусто",

    # context
    "context.agent_refused": "команда недоступна агенту драйвера",
    "context.stale": "состояние не свежее с {since}: сначала git pull",
    "context.push_failed": "push не прошёл: {error}",
    "context.not_main_tree": "состояние должно лежать в основном дереве: {path}",
    "context.no_state": "нет состояния: запусти nod init",

    # store
    "store.bad_id": "недопустимый id: «{id}»",
    "store.bad_week": "недопустимая неделя: «{week}»",
    "store.duplicate_id": "дубликат id {id}: {first} и {second}",
    "store.not_found": "нет объекта «{id}» в «{folder}»",
    "store.bad_frame_ext": "кадр: недопустимое расширение «{ext}»",
    "store.bad_toml": "недопустимый TOML: {error}",

    # model
    "model.not_tables": "недопустимый {field}: ожидался список таблиц",
    "model.missing_field": "отсутствует обязательное поле: {field}",
    "model.bad_value": "недопустимый {field}: «{value}»",

    # frontmatter
    "frontmatter.unclosed": "фронтматтер не закрыт строкой «+++»",
    "frontmatter.bad_toml": "недопустимый фронтматтер: {error}",
    "frontmatter.bad_type": "неподдерживаемый тип значения: {type}",
    "frontmatter.bad_list": "список должен состоять из строк или из таблиц",

    # git and paths
    "git.not_found": "git не найден",
    "git.detached": "не на ветке: detached HEAD",
    "git.protected_state": "ветка «{branch}» защищена: пиши состояние в рабочей ветке",
    "git.protected_commit": "ветка «{branch}» защищена: коммит идёт в рабочей ветке",
    "git.undo_not_root": "не откатить {sha}: это не первый коммит ветки",
    "git.undo_foreign": "не откатить {sha}: в первом коммите есть и {path}, вне {state}/",
    "paths.git_failed": "не удалось запустить git в «{path}»: {error}",
    "paths.not_a_repo": "«{path}» — не git-репа: {error}",
    "paths.no_main_tree": "git не вернул основное дерево для «{path}»",

    # manifest
    "harness.prompt_only": "подстановка {{{name}}} только в промпте",
    "harness.unknown_placeholder": "неизвестная подстановка {{{name}}} в команде {kind}",
    "harness.not_string": "«{key}» — не строка",
    "harness.not_table": "«{key}» — не таблица",
    "harness.not_bool": "«{key}» — не true и не false",
    "harness.unknown_key": "неизвестный ключ «{key}»",
    "harness.unknown_adapter": "адаптер «{adapter}» неизвестен: {allowed}",
    "harness.bad_lang": "lang = «{value}»: неизвестный язык, допустимо en или ru",
    "harness.missing": "нет манифеста .nod/harness.toml: запусти nod init",
    "harness.bad_toml": "недопустимый TOML в {path}: {error}",
    "harness.unreadable": "манифест {path} не читается: {error}",
    "harness.push_unread": ("предупреждение: манифест {path} не читается ({error}):"
                            " Nod работает локально, без pull и push, пока его не исправят"),
    "harness.no_value": "нет значения для {{{name}}}",

    # transitions
    "transitions.bad_result": "результат «{result}» неизвестен: {allowed}",
    "transitions.no_run": "карточка {card} в статусе {status}: ран невозможен",
    "transitions.run_open": "ран уже идёт: {run}",
    "transitions.no_step": "в карточке нет шага {step}",
    "transitions.run_finished": "ран уже завершён {finished}",
    "transitions.run_abandoned": "закрыт при старте рана {run}: карточка не выполнялась",
    "transitions.progress_line": "{now} выполнено контрактов: {done}",
    "transitions.bad_level": "уровень {level} неизвестен: 1, 2 или 3",
    "transitions.too_many_frames": "не больше шести кадров, передано {count}",
    "transitions.captions_mismatch": "подписей должно быть столько же, сколько кадров",
    "transitions.no_frame": "нет кадра «{path}»",
    "transitions.verdict_waiting": "вердикт уже ждёт ответа: {decision}",
    "transitions.verdict_question": "Принять вердикт: {title}",
    "transitions.frame_too_big": "кадр {path} больше 300 КБ, не скопирован",

    # backlog view (nod render)
    "render.head": "# {title} — печатается из .nod",
    "render.warning": "> Источник правды — .nod/. Этот файл печатает nod render {name}; правки руками теряются.",
    "render.active": "## Активные задачи (по приоритету)",
    "render.brief": "Бриф: {brief}",
    "render.done": "## ~~{title}~~ — СДЕЛАНО ({date})",
    "render.written": "записано {path}",

    # nod init
    "init.created": "создано {dir} в {parent}",
    "init.gitignore_uncommitted": ".gitignore дополнен и не закоммичен: закоммить его сам",
    "init.protected_branch": ("ветка «{branch}» защищена: Nod коммитит состояние в рабочую ветку"
                              " — создай её командой git switch -c <имя> и снова запусти nod init"),
    "init.harness_template": _HARNESS_TEMPLATE,

    # nod card
    "card.not_found": "нет карточки «{id}»",
    "card.not_in_backlog": "«{id}» нет в бэклоге",
    "card.closed": "карточка {card} уже закрыта",
    "card.closed_at": "карточка {card} уже закрыта {closed_at}",
    "card.returned": "карточка {card} уже возвращена",
    "card.return_question": "Вернуть на доработку: {title}",
    "card.show_status": "статус: {status}",
    "card.show_brief": "бриф:",
    "card.show_steps": "шаги:",

    # nod decision
    "decision.not_found": "нет решения «{id}»",
    "decision.bad_kind": "вид «{kind}» неизвестен: {allowed}",
    "decision.agent_kind": "агент драйвера не заводит решение вида «{kind}», только {allowed}",
    "decision.answered": "уже отвечено {at}",
    "decision.not_an_option": "ответ «{answer}» не из вариантов: {options}",
    "decision.row": "{id}  {kind}  {question}  → предложено: {proposed}",

    # nod run
    "run.not_found": "нет рана «{id}»",

    # nod status
    "status.waiting": "Ждёт тебя · {count}",
    "status.running": "В ране · {count}",
    "status.since": "Пока тебя не было · с {since}",
    "status.backlog": "Бэклог · {count}",
    "status.counters": "ранов {runs} · шагов {steps} · принято {accepted} · токенов {tokens}",
    "status.closed": "закрыта {id}  {title}  {closed_at}",
    "status.run_row": "{card}  {title}  шаг {step}: {step_title}  контракты {done}/{total}",
    "status.stale": "Состояние не свежее с {since}: записи отключены, сначала git pull",

    # command help
    "help.root": "путь к .nod или к корню репы",
    "help.json": "вывод в JSON",
    "help.note": "пояснение",
    "help.init": "создать .nod в репе",
    "help.card": "работа с карточками",
    "help.card_add": "добавить карточку в бэклог",
    "help.card_title": "заголовок",
    "help.card_body": "текст карточки",
    "help.card_top": "в начало бэклога",
    "help.card_move": "переставить карточку в бэклоге",
    "help.card_close": "закрыть карточку",
    "help.card_return": "вернуть карточку на доработку",
    "help.card_return_note": "что не так",
    "help.card_show": "показать карточку",
    "help.decision": "решения: вопросы владельцу",
    "help.decision_list": "показать решения без ответа",
    "help.decision_all": "вместе с отвеченными",
    "help.decision_ask": "задать вопрос (для драйвера и агентов)",
    "help.decision_kind": "вид: {kinds}",
    "help.decision_proposed": "предложенный ответ",
    "help.decision_option": "вариант ответа, повторяемо",
    "help.decision_answer": "ответить на решение",
    "help.decision_answer_value": "ответ",
    "help.decision_free": "ответ вне вариантов",
    "help.status": "показать снимок состояния",
    "help.status_since": "с какого момента считать изменения (ISO)",
    "help.status_no_sync": "не синхронизировать с git",
    "help.status_peek": "не отмечать просмотр в seen.toml",
    "help.run": "раны: start, progress, finish",
    "help.run_start": "начать ран по карточке",
    "help.run_step": "номер шага карточки",
    "help.run_contracts": "число контрактов в ране",
    "help.run_progress": "отметить прогресс рана",
    "help.run_finish": "завершить ран",
    "help.accept": "приёмка карточки: вердикт владельцу",
    "help.accept_level": "уровень проверки: 1, 2 или 3",
    "help.accept_evidence": "чем подтверждено",
    "help.accept_frame": "кадр, повторяемо",
    "help.accept_caption": "подпись к кадру",
    "help.accept_step": "проверенный шаг, повторяемо",
    "help.accept_report": "путь к отчёту",
    "help.render": "напечатать вид бэклога или архива",
    "help.render_write": "записать в файл вместо stdout",
    "help.render_path": "ПУТЬ",
    "help.driver": "драйвер: проходы по карточкам без участия человека",
    "help.driver_action": "once — один проход; install, uninstall — поставить или снять автозапуск при входе; без действия — цикл",
    "help.driver_interval": "секунд между проходами цикла",
    "help.driver_passes": "сколько проходов, 0 — без предела",
    "help.driver_dry_run": "с install или uninstall: показать, что будет сделано",
    "help.review": "обзор недели",
    "help.review_week": "собрать обзор за период и записать reviews/<неделя>.md",
    "help.review_since": "начало периода ISO, по умолчанию неделя назад",
    "help.review_mark": "отметить статус предложения обзора",
    "help.review_mark_week": "неделя обзора, например 2026-43",
    "help.review_mark_n": "номер предложения",
    "help.review_mark_status": "статус «{status}»",
    "help.doctor": "проверить машину: что проекту нужно и чего не хватает",
    "help.install": "поставить то, чего не хватает по nod doctor",
    "help.install_dry_run": "показать шаги, ничего не меняя",
    "help.mcp": "MCP-сервер по stdio для агентов",
}
