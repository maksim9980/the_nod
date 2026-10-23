"""Russian messages of `nod driver install|uninstall`: the driver autostart at login.

Literal braces are doubled: every message goes through `str.format`.
"""

MESSAGES = {
    # dry runs
    "autostart.would_write": "записал бы {path}:",
    "autostart.would_run": "запустил бы:",
    "autostart.would_remove": "удалил бы {path}",
    "autostart.with_systemd": "с systemd --user:",
    "autostart.without_systemd": "без systemd --user — вместо этого строка crontab (заменит строки с хвостом {tag}):",
    "autostart.would_drop_cron": "убрал бы из crontab строки с хвостом {tag}",

    # real runs
    "autostart.wrote": "записано {path}",
    "autostart.removed": "удалено {path}",
    "autostart.cron_set": "строка crontab записана: {line}",
    "autostart.cron_dropped": "строки crontab с хвостом {tag} убраны",
    "autostart.cron_path_cut": "строка crontab не длиннее {limit} байт: PATH сокращён с {total} до {kept} каталогов",
    "autostart.cron_path_gone": "строка crontab не длиннее {limit} байт, ни один из {total} каталогов PATH не помещается: "
                                "задача получит PATH по умолчанию от cron",
    "autostart.cron_claude_dropped": "{folder} с claude пришлось вырезать из PATH: "
                                     "задача, запущенная cron, не найдёт claude",

    # refusals
    "autostart.tr_too_long": "команда задачи — {length} символов, schtasks принимает не больше {limit}: "
                             "перенеси репу на путь короче или поставь Nod через pip в короткий путь",
    "autostart.unit_failed": "{command} вернул код {code}: {path} удалён, задача не поставлена",
    "autostart.disable_failed": "{command} вернул код {code}: {path} оставлен",
    "autostart.run_failed": "не удалось запустить {program}: {error}",
}
