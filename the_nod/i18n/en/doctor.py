"""English messages of `nod doctor`, `nod install` and the `[needs]` section of the manifest.

Literal braces are doubled: every message goes through `str.format`.
"""

MESSAGES = {
    # the table
    "doctor.col_need": "need",
    "doctor.col_have": "have",
    "doctor.col_fix": "fix",
    "doctor.yes": "yes",
    "doctor.no": "no",
    "doctor.source_env": "environment",

    # JSON files read by doctor
    "doctor.json_syntax": "{path} is unreadable: {error} (line {line})",
    "doctor.json_unreadable": "{path} is unreadable: {error}",
    "doctor.json_not_object": "{path}: expected an object",

    # python, nod, claude
    "doctor.python_unavailable": "python in PATH does not start (no Python, or the Microsoft Store stub)",
    "doctor.python_unavailable_posix": "python3 and python in PATH do not start",
    "doctor.python_found": "found {version}",
    "doctor.python_fix": "install Python ≥ {version} from python.org and add python to PATH",
    "doctor.python_fix_posix": "install Python ≥ {version} (python.org or your package manager) so that python3 is in PATH",
    "doctor.nod_module": "module the_nod",
    "doctor.not_in_path": "{word} is not in PATH",
    "doctor.nod_fix_package": "install the package the-nod",
    "doctor.claude_not_in_path": "not in PATH",
    "doctor.claude_fix": "install Claude Code and check PATH",

    # the plugin
    "doctor.plugin_name": "nod plugin",
    "doctor.plugin_double": "{detail} — double load",
    "doctor.plugin_twice": "installed twice: {names}",
    "doctor.plugin_twice_fix": "remove the extra one: {command}",
    "doctor.plugin_also_dirs": "installed and also in {key} ({sources})",
    "doctor.plugin_double_fix": "remove the path from env in ~/.claude/settings.json: the plugin loads by itself",
    "doctor.plugin_version": "{version} from {marketplace}",
    "doctor.plugin_via_dirs": "via {key}",
    "doctor.plugin_missing": "not installed",
    "doctor.plugin_install_fix": "claude plugin marketplace add {where}; claude plugin install {plugin}",
    "doctor.plugin_unknown_root": "<Nod folder or repo>",

    # the MCP server of the plugin on macOS and Linux
    "doctor.mcp_name": "MCP server",
    "doctor.mcp_missing": "no working python in PATH; the plugin starts its MCP server with it",
    "doctor.mcp_fix": 'Debian/Ubuntu: sudo apt install python-is-python3; macOS: ln -s "$(command -v python3)" <folder in PATH>/python',

    # the driver job
    "doctor.job_name": "driver job",
    "doctor.job_present": "exists",
    "doctor.job_missing": 'job "{name}" not found',
    "doctor.job_stale": "points to {path}",

    # copies into ~/.claude
    "doctor.copy_no_source": "no source in the repo",
    "doctor.copy_no_source_fix": "put the file in the repo or remove it from [needs]",
    "doctor.copy_same": "matches",
    "doctor.copy_extra": "extra files: {files}",
    "doctor.copy_differs": "differs",
    "doctor.copy_absent": "not in ~/.claude",

    # the [needs] section
    "needs.not_table": '"needs" is not a table',
    "needs.unknown_key": 'unknown key "needs.{key}"',
    "needs.not_string": '"needs.{key}" is not a string',
    "needs.not_strings": '"needs.{key}" is not a list of strings',
    "needs.bad_path": 'path needs.{key} "{path}" must be relative and inside the repo',
    "needs.unknown_job": 'needs.jobs: unknown job "{job}", known: {known}',
    "needs.bad_python": 'needs.python "{value}": expected a version like 3.13',

    # nod install
    "install.nothing": "nothing to do",
    "install.already": "already in place",
    "install.extra_left": "extra files in {path}, remove them by hand: {files}",
    "install.would_copy": "would copy {path}",
    "install.copied": "copied {path}",
    "install.copied_extra": "copied {path}; extra files, remove them by hand: {files}",
    "install.done": "done",
    "install.done_with": "done: {text}",
    "install.job_step": "driver autostart",
    "install.line_manual": "by hand: {what}",
    "install.line_dry": "would do: {what}",
    "install.job_failed": "driver autostart returned code {code}",
}
