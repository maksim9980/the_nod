"""Linux and other POSIX systems: a `systemd --user` unit, or a crontab `@reboot` line without systemd."""

import posixpath
import re
import shlex
import shutil
from pathlib import Path

from the_nod.driver.autostart import (UTF8, JobStatus, Runner, Target, call, core_of, fail, job_argv, job_path,
                                      job_suffix, probe, report, show_commands, show_file)
from the_nod.driver.signals import STOP_EXIT_CODES
from the_nod.i18n import t

SYSTEMCTL = ("systemctl", "--user")
PROBE = [*SYSTEMCTL, "show-environment"]
DAEMON_RELOAD = [*SYSTEMCTL, "daemon-reload"]
CRONTAB_LIST = ["crontab", "-l"]
CRONTAB_WRITE = ["crontab", "-"]
REBOOT = "@reboot "
ENV = "/usr/bin/env"  # sets PATH for our command only: a `PATH=` line would change the foreign lines too
CRON_COMMAND_LIMIT = 990  # bytes: Debian cron takes a command of 998 bytes after `@reboot` and refuses a longer one
WINDOWS_MOUNT = re.compile(r"^/mnt/[a-z](/|$)")  # where WSL mounts the Windows drives
CRON_PERCENT = r"\%"  # cron turns a bare `%` into a newline and drops the backslash of `\%`
CRON_ERRORS = "surrogateescape"  # foreign crontab lines go back byte for byte, whatever their encoding
_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')


def unit_name(repo: Path) -> str:
    return f"nod-driver-{job_suffix(repo)}.service"


def tag(repo: Path) -> str:
    """The tail that marks our crontab line."""
    return f"# nod-driver-{job_suffix(repo)}"


def unit_dir(target: Target) -> Path:
    base = target.env.get("XDG_CONFIG_HOME", "")
    return (Path(base) if base.strip() else target.home / ".config") / "systemd" / "user"


# --- the unit ---

def exec_quote(arg: str, *, expand: bool = True) -> str:
    """One quoted word of a unit: C escapes and `%` specifiers escaped, and `$` where systemd expands variables.

    systemd expands `$` in the arguments of `ExecStart=`, not in the program path and not in `Environment=`.
    """
    text = arg.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    if expand:
        text = text.replace("$", "$$")
    return f'"{text}"'


def exec_unquote(text: str, *, expand: bool = True) -> str:
    """The inverse of `exec_quote` for one quoted word."""
    inner = text[1:-1] if len(text) >= 2 and text[0] == text[-1] == '"' else text
    inner = re.sub(r"\\(.)", r"\1", inner).replace("%%", "%")
    return inner.replace("$$", "$") if expand else inner


def exec_line(argv: list[str]) -> str:
    program, *args = argv
    return " ".join([exec_quote(program, expand=False), *(exec_quote(arg) for arg in args)])


def unit_text(target: Target, repo: Path) -> str:
    name = repo.name.replace("%", "%%")
    path = job_path(target)
    environment = f"Environment={exec_quote(f'PATH={path}', expand=False)}\n" if path is not None else ""
    return (f"[Unit]\nDescription=Nod driver {name}\n\n"
            f"[Service]\n{environment}ExecStart={exec_line(job_argv(target, repo))}\n"
            f"SuccessExitStatus={' '.join(map(str, STOP_EXIT_CODES))}\n\n"
            "[Install]\nWantedBy=default.target\n")


def _enable(unit: str) -> list[str]:
    return [*SYSTEMCTL, "enable", "--now", unit]


def _disable(unit: str) -> list[str]:
    return [*SYSTEMCTL, "disable", "--now", unit]


def _install_unit(repo: Path, path: Path, *, target: Target, run: Runner) -> int:
    """Writes the unit, reloads systemd and enables it; a failed step takes the unit away again.

    Status means "the unit file exists", so a unit left after a failure would pass doctor
    and keep `nod install` from trying again.
    """
    unit = unit_name(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(unit_text(target, repo), encoding=UTF8, errors="surrogateescape")
    print(t("autostart.wrote", path=path))
    for argv in (DAEMON_RELOAD, _enable(unit)):
        code = report(call(run, argv))
        if code != 0:
            probe(run, _disable(unit))
            path.unlink(missing_ok=True)
            probe(run, DAEMON_RELOAD)
            fail(t("autostart.unit_failed", command=shlex.join(argv), code=code, path=path))
            return code
    return 0


def _uninstall_unit(repo: Path, path: Path, *, run: Runner) -> int:
    """Disables and removes the unit; a failed `disable` keeps the unit file and gives its code."""
    unit = unit_name(repo)
    argv = _disable(unit)
    done = probe(run, argv)  # no systemctl at all: nothing to disable, the file is inert
    if done is not None and done.returncode != 0:
        code = report(done)
        fail(t("autostart.disable_failed", command=shlex.join(argv), code=code, path=path))
        return code
    path.unlink(missing_ok=True)
    print(t("autostart.removed", path=path))
    probe(run, DAEMON_RELOAD)
    return 0


# --- the crontab ---

def _cron_command(target: Target, repo: Path, path: str | None) -> str:
    argv = job_argv(target, repo) if path is None else [ENV, f"PATH={path}", *job_argv(target, repo)]
    return f"{shlex.join(argv).replace('%', CRON_PERCENT)} {tag(repo)}"


def _cron_size(command: str) -> int:
    """What cron counts: the bytes of the command, encoded as `_write_cron` hands it to `crontab -`."""
    return len(command.encode(UTF8, CRON_ERRORS))


def _folder(entry: str) -> str:
    return entry.rstrip("/") or "/"


def _claude_folder(path: str) -> str | None:
    """The folder of `claude` as the shell with this PATH would find it; `None` when the PATH has none."""
    found = shutil.which("claude", path=path)
    return _folder(posixpath.dirname(found)) if found else None


def cron_path(target: Target, repo: Path) -> str | None:
    """The PATH of the crontab line: that of the shell, or a shorter one when cron would refuse the line.

    WSL appends the Windows PATH to its own, and Debian cron answers a command over its limit with
    "command too long". Duplicates go first, then the Windows drives, then entries from the end.
    The folder of `claude` stays through all of it, unless it does not fit even alone.
    """
    path = job_path(target)

    def fits(entries: list[str]) -> bool:
        return _cron_size(_cron_command(target, repo, ":".join(entries))) <= CRON_COMMAND_LIMIT

    if path is None or fits(path.split(":")):
        return path
    kept = list(dict.fromkeys(path.split(":")))
    if fits(kept):
        return ":".join(kept)
    folder = _claude_folder(path)
    claude = next((entry for entry in kept if folder is not None and _folder(entry) == folder), None)
    if claude is not None and not fits([claude]):
        claude = None  # it cannot stay, and the others should not go for nothing
    kept = [entry for entry in kept if entry == claude or not WINDOWS_MOUNT.match(entry)]
    while kept and not fits(kept):
        kept.pop(max(index for index, entry in enumerate(kept) if entry != claude))
    return ":".join(kept) or None


def cron_line(target: Target, repo: Path) -> str:
    """The `@reboot` line with our tag at the end; `sh` reads the tag as a comment."""
    return f"{REBOOT}{_cron_command(target, repo, cron_path(target, repo))}"


def _cut_note(target: Target, repo: Path) -> None:
    """Says so when `cron_path` had to cut the PATH of the shell, and when the cut took `claude` along."""
    path, cut = job_path(target), cron_path(target, repo)
    if path is None or cut == path:
        return
    total = len(path.split(":"))
    if cut is None:
        print(t("autostart.cron_path_gone", limit=CRON_COMMAND_LIMIT, total=total))
    else:
        print(t("autostart.cron_path_cut", limit=CRON_COMMAND_LIMIT, total=total, kept=len(cut.split(":"))))
    folder = _claude_folder(path)
    if folder is not None and (cut is None or folder not in {_folder(entry) for entry in cut.split(":")}):
        print(t("autostart.cron_claude_dropped", folder=folder))


def _ours(line: str, repo: Path) -> bool:
    return line.rstrip().endswith(tag(repo))


def _cron_lines(run: Runner, *, strict: bool) -> list[str] | None:
    """The lines of the user's crontab, split on `\\n` only; no crontab gives `[]`, no crontab program `None`.

    The bytes are read as they are: no newline translation, undecodable bytes kept as surrogates.
    """
    done = call(run, CRONTAB_LIST, encoding=None) if strict else probe(run, CRONTAB_LIST, encoding=None)
    if done is None:
        return None
    if done.returncode != 0:
        return []
    lines = done.stdout.decode(UTF8, CRON_ERRORS).split("\n")
    return lines[:-1] if lines[-1] == "" else lines


def _write_cron(run: Runner, lines: list[str]) -> int:
    data = "".join(f"{line}\n" for line in lines).encode(UTF8, CRON_ERRORS)
    return report(call(run, CRONTAB_WRITE, feed=data, encoding=None))


def _install_cron(repo: Path, *, target: Target, run: Runner) -> int:
    lines = [line for line in _cron_lines(run, strict=True) if not _ours(line, repo)]
    line = cron_line(target, repo)
    code = _write_cron(run, [*lines, line])
    if code == 0:
        _cut_note(target, repo)
        print(t("autostart.cron_set", line=line))
    return code


def _uninstall_cron(repo: Path, *, run: Runner) -> int:
    lines = _cron_lines(run, strict=False)
    if not lines or not any(_ours(line, repo) for line in lines):
        return 0
    code = _write_cron(run, [line for line in lines if not _ours(line, repo)])
    if code == 0:
        print(t("autostart.cron_dropped", tag=tag(repo)))
    return code


# --- the entry points ---

def install(repo: Path, *, target: Target, run: Runner, dry_run: bool) -> int:
    path = unit_dir(target) / unit_name(repo)
    if dry_run:
        print(t("autostart.with_systemd"))
        show_file(path, unit_text(target, repo))
        show_commands([shlex.join(DAEMON_RELOAD), shlex.join(_enable(unit_name(repo)))])
        print(t("autostart.without_systemd", tag=tag(repo)))
        _cut_note(target, repo)
        print(cron_line(target, repo))
        return 0
    found = probe(run, PROBE)
    if found is not None and found.returncode == 0:
        return _install_unit(repo, path, target=target, run=run)
    return _install_cron(repo, target=target, run=run)


def uninstall(repo: Path, *, target: Target, run: Runner, dry_run: bool) -> int:
    unit = unit_name(repo)
    path = unit_dir(target) / unit
    if dry_run:
        show_commands([shlex.join(_disable(unit)), shlex.join(DAEMON_RELOAD)])
        print(t("autostart.would_remove", path=path))
        print(t("autostart.would_drop_cron", tag=tag(repo)))
        return 0
    unit_code = _uninstall_unit(repo, path, run=run) if path.exists() else 0
    cron_code = _uninstall_cron(repo, run=run)
    return unit_code or cron_code


# --- status ---

def _unit_args(path: Path) -> list[str] | None:
    """The arguments of the unit's `ExecStart=`; an unreadable unit gives `None`."""
    try:
        text = path.read_text(encoding=UTF8, errors="surrogateescape")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("ExecStart="):
            words = [match.group(0) for match in _QUOTED.finditer(line)]
            return [exec_unquote(word, expand=index > 0) for index, word in enumerate(words)]
    return None


def _cron_args(line: str, repo: Path) -> list[str] | None:
    command = line.rstrip()[: -len(tag(repo))].strip()
    command = command.removeprefix(REBOOT.strip()).strip().replace(CRON_PERCENT, "%")
    try:
        return shlex.split(command)
    except ValueError:
        return None


def _status_of(args: list[str] | None, target: Target, fallback: str) -> JobStatus:
    if not args:
        return JobStatus(True, False, fallback)
    core = core_of(args)
    return JobStatus(True, core == str(target.core), core or fallback)


def status(repo: Path, *, target: Target, run: Runner) -> JobStatus:
    path = unit_dir(target) / unit_name(repo)
    if path.is_file():
        return _status_of(_unit_args(path), target, str(path))
    for line in _cron_lines(run, strict=False) or []:
        if _ours(line, repo):
            return _status_of(_cron_args(line, repo), target, line)
    return JobStatus(False, False, unit_name(repo))
