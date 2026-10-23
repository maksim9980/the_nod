"""Russian messages of the weekly review: the file body, the summary line, the suggestions and the errors.

Literal braces are doubled: every message goes through `str.format`.
Words that take a plural form come in three messages (`_one`, `_few`, `_many`): 1 and 21 take the first,
2-4 and 22-24 the second, 5-20 and 25-30 the third (`the_nod.review.plural`).
"""

MESSAGES = {
    # words
    "review.none": "нет",
    "review.months": "янв фев мар апр мая июн июл авг сен окт ноя дек",
    "review.decimal": ",",
    "review.running": "идёт",
    "review.attempt_one": "попытка",
    "review.attempt_few": "попытки",
    "review.attempt_many": "попыток",
    "review.stop_one": "стоп",
    "review.stop_few": "стопа",
    "review.stop_many": "стопов",
    "review.time_one": "раз",
    "review.time_few": "раза",
    "review.time_many": "раз",

    # the file body and the summary
    "review.title": "# Обзор недели {week} ({period})",
    "review.totals": "ранов {runs} · шагов {steps} · стопов {stops} · принято {accepted} · токенов {tokens}"
                     " · {minutes} мин · коммитов {commits}",
    "review.h_improve": "## Что улучшить",
    "review.h_cards": "## По карточкам",
    "review.h_kinds": "## По командам агентов",
    "review.h_costly": "## Самые дорогие",
    "review.h_failures": "## Самые неудачные",
    "review.h_answers": "## Ответы владельца",
    "review.no_suggestions": "Предложений нет: данные в норме.",
    "review.cols_cards": "Карточка|Заголовок|Брифов|Ранов|Стопов|Приёмок|Токены|Статус",
    "review.cols_kinds": "Команда|Вызовов|Токены|Медиана|Наибольшее|Минуты",
    "review.cols_costly": "Что|Карточка|Токены|Минуты|Итог",
    "review.line_repeats": "Повторы: {value}",
    "review.line_stops": "Стопы: {value}",
    "review.line_stuck": "Зависания: {value}",
    "review.line_failed_briefs": "Брифы не получились: {value}",
    "review.stop_entry": "{id} ({card}, шаг {step})",
    "review.repeat_entry": "{card} шаг {step} — {count} {times}",
    "review.run_label": "{id} шаг {step}",
    "review.answers": "Задано {asked}, отвечено {answered}, {tail}",
    "review.answers_median": "медиана ожидания ответа {hours} ч.",
    "review.answers_no_median": "медиана — нет.",
    "review.open_decision": "- {id} «{question}» — {hours} ч (создано {created})",
    "review.summary_title": "Обзор недели {week} ({period}): {totals}",
    "review.summary_improve": "Что улучшить:",
    "review.summary_written": "записано {path}",

    # suggestions
    "review.s_brief_attempts": "Карточка {card} «{title}»: {count} {attempts} брифа. Проверь текст карточки и"
                               " промпт брифа адаптера: вопросы к владельцу должны идти развилками, а не повторами.",
    "review.s_expensive_run": "Ран {id} ({card}, шаг {step}): {tokens} при медиане {median}."
                              " Разбей шаг на меньшие контракты или сузь allowedTools в harness.toml.",
    "review.s_open_decision": "Решение {id} «{question}» ждёт {hours} ч."
                              " Ответь или закрой: драйвер не трогает карточку с открытым решением.",
    "review.s_stops": "Карточка {card}: {count} {stops} за период."
                      " Прочитай заметки ранов и верни карточку в бэклог или перепиши бриф.",
    "review.s_stuck": "Зависаний {count}."
                      " Проверь, что промпт рана требует `nod run progress` после каждого контракта.",
    "review.s_tool_errors": "Ран {id}: {count} ошибок инструментов."
                            " Посмотри .nod/driver/{card}.run.err.txt и allowedTools в harness.toml.",
    "review.s_unverified": "Приёмок «не проверено»: {count}."
                           " В брифе нужен сценарий проверки без рук владельца.",

    # errors and the output of `nod review`
    "review.bad_period": "период: нечитаемые границы «{since}» — «{until}»",
    "review.bad_since": "неверная дата --since: {value}",
    "review.since_not_before": "--since {value} не раньше текущего момента {now}",
    "review.no_review": "нет обзора «{week}»",
    "review.no_suggestion": "в обзоре {week} нет предложения {n}",
    "review.marked": "отмечено {n}: {status}",
}
