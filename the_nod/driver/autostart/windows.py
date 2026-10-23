"""Windows: a Task Scheduler task that starts the driver at logon."""

import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from the_nod.driver.autostart import (JobStatus, Runner, Target, call, fail, job_argv, job_suffix, probe,
                                      report, show_commands)
from the_nod.i18n import t

TR_LIMIT = 261  # schtasks refuses a longer /TR
OEM = "oem"  # the code page schtasks writes in
EXIT_REFUSED = 2
_CORE = re.compile(r'(?:^|\s)-P\s+(?:"([^"]*)"|(\S+))')


def task_name(repo: Path) -> str:
    return f"Nod driver {repo.name} {job_suffix(repo)}"


def task_command(target: Target, repo: Path) -> str:
    """The /TR value: the job command line with every path holding a space in quotes."""
    return subprocess.list2cmdline(job_argv(target, repo))


def install_argv(target: Target, repo: Path) -> list[str]:
    return ["schtasks", "/Create", "/F", "/SC", "ONLOGON", "/RL", "LIMITED",
            "/TN", task_name(repo), "/TR", task_command(target, repo)]


def uninstall_argv(repo: Path) -> list[str]:
    return ["schtasks", "/Delete", "/F", "/TN", task_name(repo)]


def install(repo: Path, *, target: Target, run: Runner, dry_run: bool) -> int:
    command = task_command(target, repo)
    # A plugin's core lives in Claude Code's cache, which the owner does not place: the message
    # points at the repo path and at a pip install into a short path instead.
    if len(command) > TR_LIMIT:
        fail(t("autostart.tr_too_long", length=len(command), limit=TR_LIMIT))
        return EXIT_REFUSED
    argv = install_argv(target, repo)
    if dry_run:
        show_commands([subprocess.list2cmdline(argv)])
        return 0
    return report(call(run, argv, encoding=OEM))


def uninstall(repo: Path, *, target: Target, run: Runner, dry_run: bool) -> int:
    argv = uninstall_argv(repo)
    if dry_run:
        show_commands([subprocess.list2cmdline(argv)])
        return 0
    return report(call(run, argv, encoding=OEM))


def _local(tag: str) -> str:
    """A tag name without its `{namespace}`."""
    return tag.rsplit("}", 1)[-1]


def task_command_of(xml_text: str) -> str:
    """<Command> and <Arguments> of the task XML joined by a space; unreadable XML gives an empty string."""
    try:
        root = ET.fromstring(xml_text.lstrip("﻿").strip())
    except ET.ParseError:
        return ""
    parts = [(node.text or "").strip() for node in root.iter() if _local(node.tag) in ("Command", "Arguments")]
    return " ".join(part for part in parts if part)


def status(repo: Path, *, target: Target, run: Runner) -> JobStatus:
    name = task_name(repo)
    done = probe(run, ["schtasks", "/Query", "/TN", name, "/XML"], encoding=OEM)
    if done is None or done.returncode != 0:
        return JobStatus(False, False, name)
    command = task_command_of(done.stdout)
    found = _CORE.search(command)
    if found is None:
        return JobStatus(True, False, command or name)
    core = found.group(1) if found.group(1) is not None else found.group(2)
    return JobStatus(True, core.casefold() == str(target.core).casefold(), core)  # Windows paths ignore case
