"""The `nod` command for the driver's agents, without pip.

The plugin ships the core as files (`python -P <plugin>/the_nod/__main__.py`), so no `nod` is on `PATH`,
while the agents may run only `nod ...` (the allowlist `Bash(nod *)`). Before every agent command the
driver writes a wrapper into `.nod/driver/bin/` and puts that folder first in the agent's `PATH`.

- `nod` is a POSIX `sh` script: macOS, Linux and Git Bash, the shell of the Claude Code Bash tool on Windows.
- `nod.cmd` (Windows only) serves cmd and PowerShell.

Every path is quoted: `C:\\Users\\Jane Doe\\...`, `~/Library/Application Support/...`.
"""

import codecs
import os
import shlex
import sys
import tempfile
from pathlib import Path, PurePath, PureWindowsPath

import the_nod
from the_nod.driver import files, guard
from the_nod.store import Store

NAME = "nod"
WRAPPERS = (NAME, f"{NAME}.cmd")  # the only files `.nod/driver/bin/` may hold
CMD_ENCODING = "oem"  # cmd reads a batch file in the console code page, the OEM one by default
CMD_ENCODING_FALLBACK = "utf-8"
# What a POSIX shell searches when `PATH` is unset: without it the agent would lose `git`, `claude` and the rest.
# Windows has no such default (the system `PATH` is always set), so only the wrapper folder stays there.
DEFAULT_PATH = os.defpath if os.name == "posix" else ""
CONSOLE_PYTHON = "python.exe"
WINDOWED_PYTHON = "pythonw.exe"


def bin_dir(store: Store) -> Path:
    """The folder of the wrappers, `.nod/driver/bin/`; absolute, as it goes into a `PATH` of another directory."""
    return files.driver_dir(store).absolute() / files.BIN_DIR


def core_path() -> Path:
    """The core entry file: it runs with `-P` and finds its own package."""
    return Path(the_nod.__file__).resolve().with_name("__main__.py")


def agent_python() -> str:
    """The interpreter of the wrapper.

    A driver started by the scheduler runs under `pythonw.exe`, which has no console: a `nod` run by an agent
    would print nowhere. The `python.exe` next to it is the console twin; without one `sys.executable` stays.
    """
    current = Path(sys.executable)
    if current.name.lower() == WINDOWED_PYTHON:
        console = current.with_name(CONSOLE_PYTHON)
        if console.exists():
            return str(console)
    return sys.executable


def env_path(bin_dir: Path, path: str) -> str:
    """`PATH` with `bin_dir` first; an empty `PATH` keeps the system default (`DEFAULT_PATH`) behind it."""
    rest = path or DEFAULT_PATH
    return os.pathsep.join([str(bin_dir), rest]) if rest else str(bin_dir)


def agent_env(store: Store) -> dict[str, str]:
    """Writes the wrappers; the environment that makes `nod` visible to the agent command (`PATH`)."""
    folder = bin_dir(store)
    sweep(folder)
    write(folder, agent_python(), core_path())
    return {"PATH": env_path(folder, os.environ.get("PATH", ""))}


def sweep(bin_dir: Path) -> None:
    """Leaves `bin_dir` a real folder with nothing but the wrappers.

    The folder is first in the agent's `PATH`, so a `git` or `claude` left there by an agent would run in place
    of the real one. Links and junctions go as links and are never followed: the folders they point to keep
    their files. A `bin_dir` that is itself a link, or not a folder, is removed; `write` makes a real one.
    """
    if guard.is_link(bin_dir) or (bin_dir.exists() and not bin_dir.is_dir()):
        guard.remove_path(bin_dir)
    if not bin_dir.is_dir():
        return
    for entry in bin_dir.iterdir():
        if entry.name in WRAPPERS and entry.is_file() and not guard.is_link(entry):
            continue
        guard.remove_path(entry)


def write(bin_dir: Path, python: str, core: PurePath, *, platform: str = sys.platform) -> list[Path]:
    """The wrappers in `bin_dir`; the paths of the files. `nod.cmd` only for `platform == "win32"`."""
    windows = platform == "win32"
    bin_dir.mkdir(parents=True, exist_ok=True)
    written = [_put(bin_dir / NAME, _sh_script(str(python), str(core), windows).encode("utf-8"), 0o755)]
    if windows:
        written.append(_put(bin_dir / f"{NAME}.cmd", _cmd_script(str(python), str(core)), 0o644))
    return written


def _sh_script(python: str, core: str, windows: bool) -> str:
    """`exec` the interpreter with the core; on Windows the paths are `C:/...`, which Git Bash understands."""
    def shown(path: str) -> str:
        return PureWindowsPath(path).as_posix() if windows else path

    return f'#!/bin/sh\nexec {shlex.quote(shown(python))} -P {shlex.quote(shown(core))} "$@"\n'


def _cmd_script(python: str, core: str) -> bytes:
    """The batch file in the code page cmd reads it in; `%` is doubled, a path can hold one."""
    def quoted(path: str) -> str:
        return '"' + path.replace("%", "%%") + '"'

    text = f"@{quoted(python)} -P {quoted(core)} %*\r\n"
    try:
        codecs.lookup(CMD_ENCODING)
        return text.encode(CMD_ENCODING)
    except (LookupError, UnicodeEncodeError):  # no OEM codec off Windows; a path the code page cannot hold
        return text.encode(CMD_ENCODING_FALLBACK)


def _put(path: Path, data: bytes, mode: int) -> Path:
    """The file through a temporary one and `os.replace`; an identical file is left as it is, only its mode is set.

    The mode goes onto the temporary file: `mkstemp` makes it 0o600, and the wrapper must not show up so for a moment.
    """
    if path.is_file() and path.read_bytes() == data:
        path.chmod(mode)
        return path
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path
