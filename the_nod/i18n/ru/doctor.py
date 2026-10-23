"""Russian messages of `nod doctor`, `nod install` and the `[needs]` section of the manifest.

Literal braces are doubled: every message goes through `str.format`.
"""

MESSAGES = {
    # the table
    "doctor.col_need": "нужно",
    "doctor.col_have": "есть",
    "doctor.col_fix": "чем лечится",
    "doctor.yes": "да",
    "doctor.no": "нет",
    "doctor.source_env": "окружение",

    # JSON files read by doctor
    "doctor.json_syntax": "{path} не читается: {error} (строка {line})",
    "doctor.json_unreadable": "{path} не читается: {error}",
    "doctor.json_not_object": "{path}: ждал объект",

    # python, nod, claude
    "doctor.python_unavailable": "python в PATH не запускается (нет Python или заглушка Microsoft Store)",
    "doctor.python_unavailable_posix": "python3 и python в PATH не запускаются",
    "doctor.python_found": "найден {version}",
    "doctor.python_fix": "поставь Python ≥ {version} с python.org и включи python в PATH",
    "doctor.python_fix_posix": "поставь Python ≥ {version} (python.org или пакетный менеджер), чтобы python3 был в PATH",
    "doctor.nod_module": "модуль the_nod",
    "doctor.not_in_path": "{word} не в PATH",
    "doctor.nod_fix_package": "поставь пакет the-nod",
    "doctor.claude_not_in_path": "не в PATH",
    "doctor.claude_fix": "установи Claude Code и проверь PATH",

    # the plugin
    "doctor.plugin_name": "плагин nod",
    "doctor.plugin_double": "{detail} — двойная загрузка",
    "doctor.plugin_twice": "установлен дважды: {names}",
    "doctor.plugin_twice_fix": "убери лишний: {command}",
    "doctor.plugin_also_dirs": "установлен и ещё в {key} ({sources})",
    "doctor.plugin_double_fix": "убери путь из env в ~/.claude/settings.json: плагин грузится сам",
    "doctor.plugin_version": "{version} из {marketplace}",
    "doctor.plugin_via_dirs": "через {key}",
    "doctor.plugin_missing": "не установлен",
    "doctor.plugin_install_fix": "claude plugin marketplace add {where}; claude plugin install {plugin}",
    "doctor.plugin_unknown_root": "<папка или репа Nod>",

    # the MCP server of the plugin on macOS and Linux
    "doctor.mcp_name": "MCP-сервер",
    "doctor.mcp_missing": "в PATH нет работающего python; им плагин запускает MCP-сервер",
    "doctor.mcp_fix": 'Debian/Ubuntu: sudo apt install python-is-python3; macOS: ln -s "$(command -v python3)" <папка из PATH>/python',

    # the driver job
    "doctor.job_name": "задача драйвера",
    "doctor.job_present": "есть",
    "doctor.job_missing": "задача «{name}» не найдена",
    "doctor.job_stale": "указывает на {path}",

    # copies into ~/.claude
    "doctor.copy_no_source": "нет источника в репе",
    "doctor.copy_no_source_fix": "положи файл в репу или убери из [needs]",
    "doctor.copy_same": "совпадает",
    "doctor.copy_extra": "лишние файлы: {files}",
    "doctor.copy_differs": "отличается",
    "doctor.copy_absent": "нет в ~/.claude",

    # the [needs] section
    "needs.not_table": "«needs» — не таблица",
    "needs.unknown_key": "неизвестный ключ «needs.{key}»",
    "needs.not_string": "«needs.{key}» — не строка",
    "needs.not_strings": "«needs.{key}» — не список строк",
    "needs.bad_path": "путь needs.{key} «{path}» должен быть относительным, внутри репы",
    "needs.unknown_job": "needs.jobs: неизвестная задача «{job}», известны: {known}",
    "needs.bad_python": "needs.python «{value}»: ожидалась версия вида 3.13",

    # nod install
    "install.nothing": "ничего не нужно",
    "install.already": "уже есть",
    "install.extra_left": "лишние файлы в {path}, убери руками: {files}",
    "install.would_copy": "скопировал бы {path}",
    "install.copied": "скопировано {path}",
    "install.copied_extra": "скопировано {path}; лишние файлы, убери руками: {files}",
    "install.done": "готово",
    "install.done_with": "готово: {text}",
    "install.job_step": "автозапуск драйвера",
    "install.line_manual": "руками: {what}",
    "install.line_dry": "сделал бы: {what}",
    "install.job_failed": "автозапуск драйвера вернул код {code}",
}
