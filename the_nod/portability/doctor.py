"""Checks the machine against the `[needs]` section: what is needed, what is there and what fixes it."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

import the_nod
from the_nod.driver import autostart
from the_nod.driver.autostart import JobStatus
from the_nod.i18n import t
from the_nod.paths import NO_WINDOW
from the_nod.portability.needs import COPY_KINDS, Needs, python_floor
from the_nod.store import Store

NONE = "—"
PYTHON_COMMANDS = ("python", "py", "python3")
FIX_INSTALL = "nod install"
FIX_JOB = "nod driver install"
PLUGIN_NAME = "nod"
PLUGIN_DIRS_KEY = "CLAUDE_CODE_PLUGIN_DIRS"
SOURCE_SETTINGS = "settings.json"
SOURCE_ENV = "env"  # an identifier; `_source_label` gives the name shown in the language
CONFIG_DIR_KEY = "CLAUDE_CONFIG_DIR"
PROBE_TIMEOUT = 15
PROBE_CODE = "import sys; print(sys.version_info[0], sys.version_info[1])"
PYTHON = "python"
PYTHON3 = "python3"
MCP_COMMAND = "python"  # the command `.claude-plugin/plugin.json` starts the MCP server with
WINDOWS = "win32"


Versions = dict[str, tuple[int, int] | None]  # a Python command → its version, `None` when it does not answer


def _not_probed() -> None:
    """The default `python3_in_path` of a machine that does not say: no `python3`."""
    return None


@dataclass(frozen=True)
class Machine:
    home: Path
    platform: str
    which: Callable[[str], str | None]
    has_module: Callable[[str], bool]
    job_status: Callable[[Path], JobStatus]
    env: Mapping[str, str] = field(default_factory=dict)
    python_in_path: Callable[[], tuple[int, int] | None] = field(kw_only=True)
    python3_in_path: Callable[[], tuple[int, int] | None] = field(kw_only=True, default=_not_probed)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    fix: str
    auto: str | None


def _probe(command: str) -> tuple[int, int] | None:
    """The version of `command` from PATH, found by running it; the Microsoft Store stub and any failure give `None`."""
    try:
        result = subprocess.run([command, "-c", PROBE_CODE], capture_output=True, text=True,
                                timeout=PROBE_TIMEOUT, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return None
    parts = result.stdout.split()
    if result.returncode != 0 or len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    return int(parts[0]), int(parts[1])


def _python_in_path() -> tuple[int, int] | None:
    """The version of `python` from PATH."""
    return _probe(PYTHON)


def _python3_in_path() -> tuple[int, int] | None:
    """The version of `python3` from PATH: the only Python command of stock Ubuntu and macOS."""
    return _probe(PYTHON3)


def _job_status(repo: Path) -> JobStatus:
    """The driver autostart job of `repo` on this machine."""
    return autostart.status(repo)


def machine() -> Machine:
    """The real machine: the only place where doctor looks at the system."""
    return Machine(home=Path.home(), platform=sys.platform, which=shutil.which,
                   has_module=lambda name: importlib.util.find_spec(name) is not None,
                   job_status=_job_status, env=dict(os.environ), python_in_path=_python_in_path,
                   python3_in_path=_python3_in_path)


def config_dir(m: Machine) -> Path:
    """The Claude configuration folder: a non-empty `CLAUDE_CONFIG_DIR`, else `~/.claude`."""
    value = m.env.get(CONFIG_DIR_KEY, "")
    return Path(value) if value.strip() else m.home / ".claude"


def plugin_root() -> Path | None:
    """The plugin root: the folder above the package, if it holds `pyproject.toml`."""
    root = Path(the_nod.__file__).resolve().parent.parent
    return root if (root / "pyproject.toml").is_file() else None


def read_json(path: Path) -> tuple[dict | None, str]:
    """A JSON object from a file: the data and an empty error; no file gives `{}`; unreadable gives `None` and the error."""
    if not path.exists():
        return {}, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        return None, t("doctor.json_syntax", path=path, error=error.msg, line=error.lineno)
    except (OSError, UnicodeDecodeError) as error:
        return None, t("doctor.json_unreadable", path=path, error=error)
    if not isinstance(data, dict):
        return None, t("doctor.json_not_object", path=path)
    return data, ""


def installed_plugins(config: Path) -> list[tuple[str, str]]:
    """Pairs (marketplace, version) of the installed nod plugin from the registry in the Claude folder `config`."""
    data, _ = read_json(config / "plugins" / "installed_plugins.json")
    plugins = (data or {}).get("plugins")
    if not isinstance(plugins, dict):
        return []
    prefix = f"{PLUGIN_NAME}@"
    result = []
    for key, entries in plugins.items():
        if not key.startswith(prefix) or not isinstance(entries, list) or not entries:
            continue
        version = entries[0].get("version") if isinstance(entries[0], dict) else None
        result.append((key[len(prefix):], version if isinstance(version, str) and version else "?"))
    return result


def _dir_sources(m: Machine) -> list[tuple[str, str]]:
    """Pairs (source, path) from `CLAUDE_CODE_PLUGIN_DIRS`: settings.json and the process environment, no empty ones."""
    data, _ = read_json(config_dir(m) / "settings.json")
    env = (data or {}).get("env")
    values = [(SOURCE_SETTINGS, env.get(PLUGIN_DIRS_KEY, "") if isinstance(env, dict) else ""),
              (SOURCE_ENV, m.env.get(PLUGIN_DIRS_KEY, ""))]
    return [(source, part.strip()) for source, value in values if isinstance(value, str)
            for part in value.split(os.pathsep) if part.strip()]


def _source_label(source: str) -> str:
    """The name of a `_dir_sources` source as shown to the reader."""
    return t("doctor.source_env") if source == SOURCE_ENV else source


def _check(name: str, ok: bool, detail: str, fix: str, auto: str | None) -> Check:
    """A passed check has nothing to fix: the fix is a dash, there is no auto."""
    return Check(name, True, detail, NONE, None) if ok else Check(name, False, detail, fix, auto)


def _quoted(path: Path) -> str:
    """A path for a command in a fix: in double quotes when it holds a space."""
    text = str(path)
    return f'"{text}"' if " " in text else text


def _versions(m: Machine) -> Versions:
    """The version of each Python command, in the order they are tried: `python` on Windows, `python3`, `python` elsewhere."""
    versions = {PYTHON: m.python_in_path()}
    if m.platform != WINDOWS:
        versions = {PYTHON3: m.python3_in_path(), **versions}
    return versions


def _shown(version: tuple[int, int]) -> str:
    return f"{version[0]}.{version[1]}"


def _python(needs: Needs, m: Machine, versions: Versions) -> Check:
    """The first command that reaches the floor; if none does, the first that answered.

    On Windows that is `python` (the Microsoft Store stub does not answer). On macOS and Linux it is `python3`,
    then `python`, and the detail names the command.
    """
    floor = python_floor(needs)
    named = m.platform != WINDOWS
    answered = [(command, found) for command, found in versions.items() if found is not None]
    best = next((pair for pair in answered if pair[1] >= floor), answered[0] if answered else None)
    suffix = f" ({best[0]})" if best is not None and named else ""
    if best is None:
        detail = t("doctor.python_unavailable_posix" if named else "doctor.python_unavailable")
    elif best[1] < floor:
        detail = t("doctor.python_found", version=_shown(best[1])) + suffix
    else:
        detail = _shown(best[1]) + suffix
    ok = best is not None and best[1] >= floor
    fix = t("doctor.python_fix_posix" if named else "doctor.python_fix", version=needs.python)
    return _check(f"python ≥ {needs.python}", ok, detail, fix, None)


def _mcp(needs: Needs, m: Machine, versions: Versions) -> list[Check]:
    """macOS and Linux: the plugin starts its MCP server as `python`, by that exact name, and stock systems only have `python3`.

    On Windows the `python` row is the same probe, so there is no row of its own.
    """
    if m.platform == WINDOWS:
        return []
    floor = python_floor(needs)
    found = versions[MCP_COMMAND]
    if found is None:
        detail = t("doctor.mcp_missing")
    elif found < floor:
        detail = t("doctor.python_found", version=_shown(found)) + f" ({MCP_COMMAND})"
    else:
        detail = f"{_shown(found)} ({MCP_COMMAND})"
    ok = found is not None and found >= floor
    return [_check(t("doctor.mcp_name"), ok, detail, t("doctor.mcp_fix"), None)]


def _nod(needs: Needs, m: Machine, root: Path | None) -> list[Check]:
    if not needs.nod.strip():
        return []
    word = needs.nod.split()[0]
    if word in PYTHON_COMMANDS:
        ok, detail = m.has_module("the_nod"), t("doctor.nod_module")
    else:
        found = m.which(word)
        ok, detail = found is not None, found or t("doctor.not_in_path", word=word)
    fix = f"pip install -e {_quoted(root)}" if root is not None else t("doctor.nod_fix_package")
    return [_check("nod", ok, detail, fix, None)]


def _claude(needs: Needs, m: Machine) -> list[Check]:
    if not needs.claude.strip():
        return []
    found = m.which(needs.claude.split()[0])
    return [_check("claude", found is not None, found or t("doctor.claude_not_in_path"),
                   t("doctor.claude_fix"), None)]


def _resolved(path: Path) -> str:
    """The path after `resolve` and `normcase`: case does not matter on Windows."""
    return os.path.normcase(str(path.resolve()))


def _manifest_is_ours(folder: Path) -> bool:
    data, _ = read_json(folder / ".claude-plugin" / "plugin.json")
    return (data or {}).get("name") == PLUGIN_NAME


def is_ours(path: Path, root: Path | None) -> bool:
    """The path is our plugin: the root of the running core, its mod, or a folder with the nod manifest (itself, parent, grandparent)."""
    if root is not None and _resolved(path) in (_resolved(root), _resolved(root / "mod" / "nod-pane")):
        return True
    return any(_manifest_is_ours(folder) for folder in (path, path.parent, path.parent.parent))


def _double(name: str, detail: str, fix: str) -> Check:
    return _check(name, False, t("doctor.plugin_double", detail=detail), fix, None)


def _plugin(m: Machine, root: Path | None) -> Check:
    name = t("doctor.plugin_name")
    known = installed_plugins(config_dir(m))
    sources = sorted({source for source, path in _dir_sources(m) if is_ours(Path(path), root)},
                     key=(SOURCE_SETTINGS, SOURCE_ENV).index)
    if len(known) > 1:
        names = ", ".join(marketplace for marketplace, _ in known)
        command = f"claude plugin uninstall {PLUGIN_NAME}@{known[-1][0]}"
        return _double(name, t("doctor.plugin_twice", names=names), t("doctor.plugin_twice_fix", command=command))
    if known and sources:
        labels = ", ".join(_source_label(source) for source in sources)
        return _double(name, t("doctor.plugin_also_dirs", key=PLUGIN_DIRS_KEY, sources=labels),
                       t("doctor.plugin_double_fix"))
    if known:
        marketplace, version = known[0]
        return _check(name, True, t("doctor.plugin_version", version=version, marketplace=marketplace), NONE, None)
    if sources:
        return _check(name, True, t("doctor.plugin_via_dirs", key=PLUGIN_DIRS_KEY), NONE, None)
    where = _quoted(root) if root is not None else t("doctor.plugin_unknown_root")
    fix = f"claude plugin install {PLUGIN_NAME} --marketplace {where}"
    return _check(name, False, t("doctor.plugin_missing"), fix, None)


def _jobs(needs: Needs, m: Machine, repo_root: Path) -> list[Check]:
    if "driver" not in needs.jobs:
        return []
    found = m.job_status(repo_root)
    if not found.installed:
        detail = t("doctor.job_missing", name=found.detail)
    elif not found.current:
        detail = t("doctor.job_stale", path=found.detail)
    else:
        detail = t("doctor.job_present")
    return [_check(t("doctor.job_name"), found.installed and found.current, detail, FIX_JOB, "job")]


def _files(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


def same_content(source: Path, target: Path) -> bool:
    """A file: equal bytes; a folder: the same set of relative paths and the bytes of each file."""
    if source.is_file():
        return target.is_file() and source.read_bytes() == target.read_bytes()
    if not target.is_dir():
        return False
    names = _files(source)
    if names != _files(target):
        return False
    return all((source / name).read_bytes() == (target / name).read_bytes() for name in names)


def extra_files(source: Path, target: Path) -> list[str]:
    """Files of the target folder that the source folder does not have, alphabetically; empty for files."""
    if not source.is_dir() or not target.is_dir():
        return []
    return sorted(_files(target) - _files(source))


def _copy(kind: str, path: str, m: Machine, repo_root: Path) -> Check:
    base = Path(path).name
    name = f"{kind}/{base}"
    source = repo_root / path
    if not source.exists():
        return _check(name, False, t("doctor.copy_no_source"), t("doctor.copy_no_source_fix"), None)
    target = config_dir(m) / kind / base
    if same_content(source, target):
        return _check(name, True, t("doctor.copy_same"), NONE, None)
    extra = extra_files(source, target)
    if extra:
        detail = t("doctor.copy_extra", files=", ".join(extra))
    else:
        detail = t("doctor.copy_differs") if target.exists() else t("doctor.copy_absent")
    return _check(name, False, detail, FIX_INSTALL, "copy")


def checks(store: Store, needs: Needs, m: Machine) -> list[Check]:
    """All the checks in order: python, nod, claude, the plugin, the MCP server (not on Windows), the driver job, copies into ~/.claude."""
    repo_root = store.root.parent
    root = plugin_root()
    versions = _versions(m)
    result = [_python(needs, m, versions), *_nod(needs, m, root), *_claude(needs, m), _plugin(m, root),
              *_mcp(needs, m, versions)]
    result += _jobs(needs, m, repo_root)
    result += [_copy(kind, path, m, repo_root) for kind in COPY_KINDS for path in getattr(needs, kind)]
    return result


def _have(check: Check) -> str:
    """The "have" column: a failed check says no and what was found; a passed one just says yes."""
    if not check.ok:
        return f"{t('doctor.no')} ({check.detail})" if check.detail else t("doctor.no")
    return t("doctor.yes")


def table(checks: list[Check]) -> str:
    """The table "need | have | fix", the columns aligned to the longest cell."""
    head = (t("doctor.col_need"), t("doctor.col_have"), t("doctor.col_fix"))
    rows = [head] + [(c.name, _have(c), NONE if c.ok else c.fix) for c in checks]
    first = max(len(row[0]) for row in rows)
    second = max(len(row[1]) for row in rows)
    return "\n".join(f"{a:<{first}}  {b:<{second}}  {c}".rstrip() for a, b, c in rows)


def all_ok(checks: list[Check]) -> bool:
    return all(check.ok for check in checks)
