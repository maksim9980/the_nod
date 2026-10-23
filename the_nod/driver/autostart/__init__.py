"""`nod driver install|uninstall`: the driver starts at login.

Windows uses a Task Scheduler task, macOS a LaunchAgent, Linux (and any other POSIX system)
a `systemd --user` unit or, without systemd, a crontab `@reboot` line. Everything that
depends on the machine is in `Target`, and every command goes through `run`: tests inject both.
"""

import hashlib
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import the_nod
from the_nod.context import CliError
from the_nod.i18n import t
from the_nod.paths import NO_WINDOW

Runner = Callable[..., subprocess.CompletedProcess]
SUFFIX_LENGTH = 8
UTF8 = "utf-8"


@dataclass(frozen=True)
class Target:
    """The machine the job is set up on."""

    platform: str  # "win32" | "darwin" | "linux"; any other value is handled as Linux
    home: Path
    python: str  # the interpreter the job runs: pythonw.exe next to python on Windows, else sys.executable
    core: Path  # .../the_nod/__main__.py
    uid: int | None  # the gui/<uid> domain of launchctl; None on Windows
    env: Mapping[str, str]  # for XDG_CONFIG_HOME


@dataclass(frozen=True)
class JobStatus:
    installed: bool
    current: bool  # the job runs exactly `core`
    detail: str  # the job name when it is missing; the core path the job runs when it is installed


def core_main() -> Path:
    """The package entry the job runs with `python -P`."""
    return Path(the_nod.__file__).resolve().with_name("__main__.py")


def _python() -> str:
    """pythonw.exe on Windows when it exists (no console window at logon), else this interpreter."""
    if sys.platform == "win32":
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return sys.executable


def current_target() -> Target:
    """This machine: the only place where autostart looks at the system."""
    uid = os.getuid() if hasattr(os, "getuid") else None
    return Target(platform=sys.platform, home=Path.home(), python=_python(), core=core_main(), uid=uid,
                  env=dict(os.environ))


def job_suffix(repo: Path) -> str:
    """Tells the jobs of two repos with the same folder name apart."""
    return hashlib.sha256(str(repo.resolve()).encode(UTF8)).hexdigest()[:SUFFIX_LENGTH]


def job_argv(target: Target, repo: Path) -> list[str]:
    return [target.python, "-P", str(target.core), "--root", str(repo), "driver"]


def job_path(target: Target) -> str | None:
    """The PATH the job gets on macOS and Linux: that of the shell running `nod driver install`.

    launchd, `systemd --user` and cron start jobs with a short PATH where `claude` from
    `~/.local/bin` or Homebrew is not found. Installing again refreshes it.
    """
    value = target.env.get("PATH", "")
    return value if value.strip() else None


def core_of(argv: list[str]) -> str | None:
    """The core path in a job command: the argument after `-P`."""
    if "-P" not in argv:
        return None
    index = argv.index("-P") + 1
    return argv[index] if index < len(argv) else None


# --- running commands and showing them ---

def _kwargs(feed: str | bytes | None, encoding: str | None) -> dict:
    """Output captured as text in `encoding`, or as bytes when it is `None`; stdin is `feed`, or nothing at all."""
    kwargs: dict = {"capture_output": True, "creationflags": NO_WINDOW}
    if encoding is not None:
        kwargs.update(text=True, encoding=encoding, errors="replace")
    if feed is None:
        kwargs["stdin"] = subprocess.DEVNULL
    else:
        kwargs["input"] = feed
    return kwargs


def call(run: Runner, argv: list[str], *, feed: str | bytes | None = None, encoding: str | None = UTF8):
    """Runs `argv` with its output captured; a program that does not start is a `CliError`."""
    try:
        return run(argv, **_kwargs(feed, encoding))
    except OSError as err:
        raise CliError(t("autostart.run_failed", program=argv[0], error=err)) from err


def probe(run: Runner, argv: list[str], *, encoding: str | None = UTF8):
    """Like `call`, but a program that does not start gives `None`: for status checks and probes."""
    try:
        return run(argv, **_kwargs(None, encoding))
    except OSError:
        return None


def _said(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(UTF8, "replace").strip()
    return (value or "").strip()


def report(done) -> int:
    """Prints what a command said and returns its exit code."""
    if out := _said(done.stdout):
        print(out)
    if err := _said(done.stderr):
        print(err, file=sys.stderr)
    return done.returncode


def fail(message: str) -> None:
    """An error line on stderr, in the form the CLI uses."""
    print(t("cli.error", message=message), file=sys.stderr)


def show_file(path: Path, content: str) -> None:
    print(t("autostart.would_write", path=path))
    print(content.rstrip("\n"))


def show_commands(lines: list[str]) -> None:
    print(t("autostart.would_run"))
    for line in lines:
        print(line)


# --- the entry points ---

def _backend(platform: str) -> ModuleType:
    from the_nod.driver.autostart import linux, macos, windows
    return {"win32": windows, "darwin": macos}.get(platform, linux)


def install(repo: Path, *, dry_run: bool, target: Target | None = None, run: Runner = subprocess.run) -> int:
    """Sets up the job; with `dry_run` prints the files and the commands and changes nothing."""
    target = target or current_target()
    return _backend(target.platform).install(repo, target=target, run=run, dry_run=dry_run)


def uninstall(repo: Path, *, dry_run: bool, target: Target | None = None, run: Runner = subprocess.run) -> int:
    """Removes the job; with `dry_run` prints the commands and changes nothing."""
    target = target or current_target()
    return _backend(target.platform).uninstall(repo, target=target, run=run, dry_run=dry_run)


def status(repo: Path, *, target: Target | None = None, run: Runner = subprocess.run) -> JobStatus:
    """Whether the job exists and runs `target.core`; reads only."""
    target = target or current_target()
    return _backend(target.platform).status(repo, target=target, run=run)
