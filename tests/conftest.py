import re
import subprocess
from pathlib import Path

import pytest

from the_nod import i18n

BRANCH = "2026-10-20"


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout


_PUSH_OFF = re.compile(r"^push = false$", re.MULTILINE)


def enable_push(repo: Path) -> None:
    """Turns on `[git] push` in the manifest of `repo` and commits it.

    For tests that need a remote: pull before a write, push after it, the lock that needs the push.
    A state without a manifest (`seed`) gets one with the `[git]` table only.
    The commit stays local; the next write of Nod pushes it.
    """
    path = repo / ".nod" / "harness.toml"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if _PUSH_OFF.search(text):
        text = _PUSH_OFF.sub("push = true", text)
    else:
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + "[git]\npush = true\n"
    path.write_text(text, encoding="utf-8")
    git(repo, "add", ".nod/harness.toml")
    git(repo, "commit", "-q", "-m", "state: push on")


@pytest.fixture(autouse=True)
def default_lang(monkeypatch):
    """Every test starts in English without NOD_LANG; a test that switches the language leaves no trace."""
    monkeypatch.delenv(i18n.ENV, raising=False)
    i18n.use(i18n.DEFAULT)
    yield
    i18n.use(i18n.DEFAULT)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo with one commit, branch 2026-10-20 and a bare remote `origin`."""
    root = tmp_path / "repo"
    root.mkdir()
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare")
    git(root, "init", "-b", BRANCH)
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.com")
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "init")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-u", "origin", BRANCH)
    return root


@pytest.fixture
def worktree(repo: Path) -> Path:
    """A second worktree of the repo on branch 2026-10-20-run-1."""
    path = repo.parent / "wt"
    git(repo, "worktree", "add", str(path), "-b", f"{BRANCH}-run-1")
    return path
