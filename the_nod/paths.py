"""Paths: the `.nod/` state folder, the main git worktree, the machine name."""

import socket
import subprocess
import sys
from pathlib import Path

from the_nod.i18n import t

STATE_DIR_NAME = ".nod"
# Under pythonw.exe (a scheduler task) every git and claude would otherwise open its own console window.
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_WORKTREE_PREFIX = "worktree "


class NotARepo(RuntimeError):
    """The path is outside a git repository, or git is not available."""


def find_state_dir(start: Path) -> Path | None:
    """Looks for `.nod/` from `start` up to the root of the drive."""
    start = Path(start).absolute()
    for folder in (start, *start.parents):
        candidate = folder / STATE_DIR_NAME
        if candidate.is_dir():
            return candidate
    return None


def main_worktree_root(path: Path) -> Path:
    """Root of the main worktree of the repository that holds `path`."""
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain", "-z"],
            cwd=path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=NO_WINDOW,
            stdin=subprocess.DEVNULL,
        )
    except OSError as err:
        raise NotARepo(t("paths.git_failed", path=path, error=err)) from err
    if result.returncode != 0:
        raise NotARepo(t("paths.not_a_repo", path=path, error=result.stderr.strip()))
    first = result.stdout.split("\0", 1)[0]
    if not first.startswith(_WORKTREE_PREFIX):
        raise NotARepo(t("paths.no_main_tree", path=path))
    return Path(first[len(_WORKTREE_PREFIX):]).resolve()


def host_name() -> str:
    """Name of this machine."""
    return socket.gethostname()
