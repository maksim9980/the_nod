"""Russian messages of the driver: the same keys and placeholders as `the_nod.i18n.en.driver`.

Literal braces are doubled (`{{name}}`): every message goes through `str.format`.
"""

MESSAGES = {
    # one pass and the loop
    "driver.pass": "проход: {did} — {message}",
    "driver.stopped": "остановлен владельцем",
    "driver.stale": "состояние не свежее с {since}",
    "driver.busy": "драйвер уже запущен",
    "driver.busy_pid": "драйвер уже запущен (pid {pid})",
    "driver.rebrief": "повторный бриф {card}",
    "driver.failed": "{action}: не удалось, см. driver.log",
    "driver.too_many_reactions": "реакций больше {limit} за проход: остальные — в следующем",
    "driver.nothing_to_do": "нечего делать",
    "driver.dirty_tree": "грязное дерево: {paths}",
    "driver.pass_aborted": "проход прерван: {error}",
    "driver.dry_run_autostart_only": "--dry-run работает только с install и uninstall: проход запускает агента",
    "driver.other_host": "драйвер этого проекта работает на {host}",

    # the lock
    "driver.foreign": "работа идёт на {host} с {at}",
    "driver.push_failed": "push не прошёл",
    "driver.lock_not_taken": "замок не получен: {reason}",
    "driver.heartbeat_stale": "состояние не свежее",
    "driver.heartbeat_foreign": "чужой замок",

    # decisions the driver asks and its reactions to the answers
    "driver.pain_question": "Бэклог пуст. Что болит?",
    "driver.batch_question": "Запустить следующую пачку? Карточек: {n}.",
    "driver.asked_batch": "спросил про следующую пачку: {id}",
    "driver.asked_pain": "спросил, что болит: {id}",
    "driver.owner_note": "Замечание владельца: {note}",
    "driver.return_reason": "Почему карточка вернулась: {reason}",
    "driver.forks_as_proposed": "развилки {card} приняты как предложено: ready",
    "driver.answer_unknown": "ответ «{answer}» на {kind} {id} непонятен драйверу: отмечен учтённым",
    "driver.batch_started": "пачка запущена: {cards}",
    "driver.pain_card": "из ответа «что болит» заведена карточка {card}",
    "driver.decision_unreadable": "решение {id} не читается: {error}",
    "driver.reaction_skipped": "решение {id}: карточка {card} в статусе {status}, реакция пропущена",

    # the answers file the agent reads
    "driver.answers_title": "# Ответы владельца по карточке {title}",
    "driver.answers_none": "Ответов нет.",
    "driver.answer": "Ответ: {answer}",

    # what only the owner can do
    "driver.auth_needed": "Войди в claude: в терминале выполни claude /login. Ответ claude: {text}",
    "driver.owner_action_reason": "команда {kind} ждёт действия владельца",
    "driver.waits_owner": "{kind} {card} ждёт владельца: {text}",
    "driver.waits_owner_note": "ждёт владельца: {text}",
    "driver.kind_brief": "бриф",
    "driver.kind_run": "ран",
    "driver.kind_accept": "приёмка",

    # the agent command
    "driver.output": "вывод {kind} {card}: код {code}, {seconds} с, файлы {out}, {err}",
    "driver.output_not_saved": "вывод {kind} {card} не сохранён: {error}",
    "driver.claude_summary": "итог claude {kind} {card}: {summary}",
    "driver.claude_line": "subtype {subtype}, is_error {is_error}, terminal_reason {reason}, ходов {turns}, $ {cost}",
    "driver.spend": "расход {kind} {card}: токены {tokens}, минуты {minutes}, $ {cost}",
    "driver.spend_dirty": "расход {kind} {card} не записан в usage/: в .nod остались правки агента",
    "driver.spend_not_written": "расход {kind} {card} не записан в usage/: {error}",
    "driver.command_stuck": "команда зависла: нет вывода дольше срока",
    "driver.command_spawn_failed": "команда не запустилась: {error}",
    "driver.command_exit": "команда вышла с кодом {code}",
    "driver.command_exit_tail": "команда вышла с кодом {code}: {tail}",
    "driver.hooks_dropped": "агент положил файлы в папку хуков {folder}: удалены",
    "driver.hooks_changed": "агент изменил .git/hooks или конфиг git: {names} — проверь и удали",
    "driver.unwritable": ("решение владельцу не записано: в .nod остались правки агента; "
                          "следующий проход откажет на грязном дереве"),
    "driver.restore_not_committed": ("восстановление {names} не записано: состояние не свежее, "
                                     "файл восстановлен локально"),
    "driver.card_unreadable": "карточка {card} не читается: {error}",

    # the brief
    "driver.brief_not_started": "бриф {card}: команда не запущена: {error}",
    "driver.brief_started": "бриф {card}: команда запущена",
    "driver.brief_stale": "состояние не свежее: результат брифа {card} не записан, файл {file}",
    "driver.brief_local": "бриф {card}: записан локально, push не прошёл",
    "driver.brief_saved": "бриф {card}: {status}, шагов {steps}, развилок {forks}",
    "driver.brief_failed": "бриф {card} не получился ({n}/{max}): {reason}",
    "driver.brief_failed_returned": "бриф {card} не получился ({n}/{max}): {reason}; карточка возвращена",
    "driver.brief_failed_note": "бриф не получился: {reason}",
    "driver.card_gone_brief": "карточка {card} исчезла во время брифа, результат в {file}",
    "driver.card_changed_brief": "карточка {card} изменена во время брифа: {status}, результат не записан",

    # a brief the agent wrote but did not commit or report
    "driver.brief_file_unreadable": "файл брифа {path} не читается: {error}",
    "driver.brief_not_committed": "бриф {path} не закоммичен: {error}",
    "driver.candidate_not_found": "бриф-кандидат не найден: {error}",
    "driver.candidate_rejected": "бриф-кандидат {path} не принят: {error}",
    "driver.previous_result_rejected": "бриф {card}: результат прошлой попытки не принят: {error}",
    "driver.previous_result_adopted": "бриф {card}: принят результат прошлой попытки: {path}",
    "driver.previous_brief_rejected": "бриф {card}: бриф прошлой попытки {path} не принят: {error}",
    "driver.previous_brief_adopted": "бриф {card}: принят бриф прошлой попытки: {path}",
    "driver.no_result_adopted": "бриф {card}: результата нет, принят бриф {path}",
    "driver.no_result_adopted_after": "бриф {card}: результата нет, принят бриф {path} (команда: {failure})",

    # the run of a step
    "driver.no_run_reason": "карточка running без рана",
    "driver.hooks_note": "агент изменил .git/hooks или конфиг git",
    "driver.stop_note": "агент остановил ран без пояснения",
    "driver.minutes": "{n} минут",
    "driver.stuck_note": "завис: {minutes} без записи",
    "driver.stuck_reason": "{minutes} без записи в ран",
    "driver.stuck_question": "Ран завис: {title}",
    "driver.run_not_started": "ран {card}: не начат: {error}",
    "driver.run_started": "ран {run} карточки {card}, шаг {step}: команда запущена",
    "driver.run_stale": "состояние не свежее: результат рана {run} не записан, файл {file}",
    "driver.run_unbuilt": "команда рана не собрана: {reason}",
    "driver.run_return_local": "ран {card}: возврат записан локально, push не прошёл",
    "driver.run_returned": "ран {card}: {note}; карточка возвращена",
    "driver.run_unreadable": "ран {run} не читается: {error}; результат в {file}",
    "driver.run_changed": "ран {run} изменён во время команды: карточка {status}, результат не записан",
    "driver.run_local": "ран {run}: записан локально, push не прошёл",
    "driver.run_ok": "ран {run} карточки {card}: ok, карточка {status}",
    "driver.run_of_card": "ран {run} карточки {card}: {note}",
    "driver.card_running_no_run": "карточка {card} в статусе running без рана",
    "driver.card_gone_run": "карточка {card} исчезла во время рана, результат в {file}",
    "driver.written_local": "{summary}: записано локально, push не прошёл",
    "driver.card_returned": "{what}; карточка возвращена",
    "driver.stuck_stale": "состояние не свежее: зависание карточки {card} не записано",
    "driver.stuck_not_written": "зависание карточки {card} не записано: {error}",
    "driver.stuck_wrong_status": "карточка {card} в статусе {status}, зависание не записано",
    "driver.stuck_wrong_run": "ран {run} не идёт по карточке {card}, зависание не записано",

    # the acceptance
    "driver.accept_wrong_status": "приёмка {card}: карточка в статусе {status}, команда не запущена",
    "driver.accept_unbuilt": "команда приёмки не собрана: {error}",
    "driver.accept_note": "приёмка {card}: {text}",
    "driver.accept_started": "приёмка {card}: команда запущена",
    "driver.accept_stale": "состояние не свежее: результат приёмки {card} не записан, файл {file}",
    "driver.accept_failed_evidence": "приёмка не получилась: {reason}",
    "driver.accept_not_written": "приёмка {card} не записана: {reason}; {error}",
    "driver.accept_local": "приёмка {card}: записана локально, push не прошёл",
    "driver.accept_done": "приёмка {card}: вердикт ждёт владельца",
    "driver.accept_failed": "приёмка {card} не получилась: {reason}; вердикт ждёт владельца",
    "driver.card_gone_accept": "карточка {card} исчезла во время приёмки, результат в {file}",
    "driver.card_changed_accept": "карточка {card} изменена во время приёмки: {status}, результат не записан",
    "driver.frame_outside": "кадр вне репы: «{path}»",

    # the guard of the agent command
    "driver.name_hooks": "папки хуков",
    "driver.name_state": "состояния .nod",
    "driver.name_state_failed": "состояния .nod (не восстановлено)",
    "driver.name_git_config": "конфиг git",
    "driver.guard_hooks": "агент положил хуки в папку драйвера — проверь",
    "driver.guard_state": "агент изменил состояние .nod — восстановлено, проверь",
    "driver.guard_manifest_origin": "агент изменил harness.toml — восстановлена версия из origin, проверь",
    "driver.guard_manifest_local": "агент изменил harness.toml — восстановлена версия из снимка до команды, проверь",
    "driver.state_not_restored": "состояние не восстановлено: {paths}",
    "driver.rollback_error": "откат дал ошибку, но дерево чистое: {paths}",
    "driver.check_failed": "сверка {name} не прошла: {error}; считаю нарушением",

    # result files and placeholders
    "driver.result_missing": "нет файла результата",
    "driver.result_no_field": "нет поля {field}",
    "driver.result_not_strings": "недопустимый {field}: ожидался список строк",
    "driver.bad_brief_path": "недопустимый путь брифа: {path}",
    "driver.unsafe_placeholder": "недопустимый символ в подстановке {{{name}}}",
    "driver.prompt_card": "## Карточка",

    # the brief parser
    "briefs.no_title": "не найдено название (строка `# …`)",
    "briefs.no_date": "не найдена дата брифа (строка `Дата: …`)",
    "briefs.no_status": "не найден статус брифа (строка `Статус: …`)",
    "briefs.fork_without_proposed": "развилка без «Предлагаю:»: {line}",
    "briefs.no_steps": "в брифе нет шагов (раздел 10)",
}
