"""macOS: a LaunchAgent in `~/Library/LaunchAgents` that starts the driver at login."""

import plistlib
import shlex
from pathlib import Path
from xml.parsers.expat import ExpatError

from the_nod.driver.autostart import (JobStatus, Runner, Target, call, core_of, job_argv, job_path, job_suffix,
                                      report, show_commands, show_file)
from the_nod.i18n import t
from the_nod.paths import STATE_DIR_NAME

LABEL_PREFIX = "the-nod.driver."


def label(repo: Path) -> str:
    return f"{LABEL_PREFIX}{job_suffix(repo)}"


def plist_path(target: Target, repo: Path) -> Path:
    return target.home / "Library" / "LaunchAgents" / f"{label(repo)}.plist"


def log_path(repo: Path) -> Path:
    """Where launchd writes the driver's stdout and stderr: a local file of the state folder."""
    return repo / STATE_DIR_NAME / "driver" / "autostart.log"


def plist_bytes(target: Target, repo: Path) -> bytes:
    log = str(log_path(repo))
    data = {"Label": label(repo), "ProgramArguments": job_argv(target, repo), "RunAtLoad": True,
            "WorkingDirectory": str(repo), "StandardOutPath": log, "StandardErrorPath": log}
    path = job_path(target)
    if path is not None:  # launchd gives a job /usr/bin:/bin:/usr/sbin:/sbin
        data["EnvironmentVariables"] = {"PATH": path}
    return plistlib.dumps(data)


def _domain(target: Target) -> str:
    return f"gui/{target.uid}"


def _bootout(target: Target, repo: Path) -> list[str]:
    return ["launchctl", "bootout", f"{_domain(target)}/{label(repo)}"]


def install(repo: Path, *, target: Target, run: Runner, dry_run: bool) -> int:
    path = plist_path(target, repo)
    data = plist_bytes(target, repo)
    bootstrap = ["launchctl", "bootstrap", _domain(target), str(path)]
    if dry_run:
        show_file(path, data.decode("utf-8"))
        show_commands([shlex.join(_bootout(target, repo)), shlex.join(bootstrap)])
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    log_path(repo).parent.mkdir(parents=True, exist_ok=True)  # launchd does not create the log folder
    path.write_bytes(data)
    print(t("autostart.wrote", path=path))
    call(run, _bootout(target, repo))  # an agent that is not loaded yet fails here: that is fine
    return report(call(run, bootstrap))


def uninstall(repo: Path, *, target: Target, run: Runner, dry_run: bool) -> int:
    path = plist_path(target, repo)
    if dry_run:
        show_commands([shlex.join(_bootout(target, repo))])
        print(t("autostart.would_remove", path=path))
        return 0
    call(run, _bootout(target, repo))  # an agent that is not loaded fails here: that is fine
    if path.exists():
        path.unlink()
        print(t("autostart.removed", path=path))
    return 0


def status(repo: Path, *, target: Target, run: Runner) -> JobStatus:
    path = plist_path(target, repo)
    if not path.is_file():
        return JobStatus(False, False, label(repo))
    try:
        data = plistlib.loads(path.read_bytes())
    except (OSError, ValueError, ExpatError):  # a broken plist is a job, but not ours to trust
        return JobStatus(True, False, str(path))
    args = data.get("ProgramArguments") if isinstance(data, dict) else None
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        return JobStatus(True, False, str(path))
    core = core_of(args)
    return JobStatus(True, str(target.core) in args, core or str(path))
