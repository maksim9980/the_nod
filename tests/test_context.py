import subprocess
from types import SimpleNamespace

import pytest

from the_nod import context
from the_nod.context import Stale
from the_nod.gitsync import GitSync, ProtectedBranch
from tests.conftest import enable_push
from tests.test_snapshot import seed


def _ctx(repo):
    return context.open(SimpleNamespace(root=str(repo)))


def test_write_commits_and_pushes(repo):
    seed(repo); enable_push(repo)
    ctx = _ctx(repo)
    assert ctx.fresh
    ctx.write("правка", lambda: (repo / ".nod" / "note.md").write_text("x", encoding="utf-8"))
    log = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=repo, capture_output=True,
                         text=True, encoding="utf-8").stdout.strip()
    assert log == "state: правка"
    assert (repo / ".nod" / "state.json").exists()


def test_write_refuses_when_stale(repo, monkeypatch):
    seed(repo); enable_push(repo)
    monkeypatch.setattr(GitSync, "pull_ff", lambda self: False)
    ctx = _ctx(repo)
    with pytest.raises(Stale, match="run git pull first"):
        ctx.write("x", lambda: None)


def test_write_refuses_on_protected_branch_before_fn(repo):
    seed(repo)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=repo, capture_output=True)
    ctx = context.open(SimpleNamespace(root=str(repo)), sync=False)  # the new main has no origin/main
    called = []
    with pytest.raises(ProtectedBranch):
        ctx.write("x", lambda: called.append(1))
    assert not called


def test_stale_cleared_after_successful_pull(repo, monkeypatch):
    s = seed(repo); enable_push(repo)
    monkeypatch.setattr(GitSync, "pull_ff", lambda self: False)
    _ctx(repo)
    assert "stale_since" in s.seen()
    monkeypatch.undo()
    assert _ctx(repo).fresh and "stale_since" not in s.seen()


def _log(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8").stdout


def test_write_reaches_remote_without_state_json(repo, tmp_path):
    seed(repo); enable_push(repo)
    ctx = _ctx(repo)
    ctx.write("правка", lambda: (repo / ".nod" / "note.md").write_text("x", encoding="utf-8"))
    remote = tmp_path / "remote.git"
    assert _log(remote, "log", "-1", "--format=%s", "2026-10-20").strip() == "state: правка"
    files = _log(remote, "show", "--name-only", "--format=", "2026-10-20").split()
    assert ".nod/note.md" in files and not any(f.endswith(("state.json", "seen.toml")) for f in files)


def test_push_failure_goes_to_stderr_exit_zero(repo, capsys, monkeypatch):
    seed(repo); enable_push(repo)
    ctx = _ctx(repo)
    monkeypatch.setattr(GitSync, "push", lambda self: setattr(self, "last_error", "refused") or False)
    ctx.write("x", lambda: (repo / ".nod" / "n.md").write_text("x", encoding="utf-8"))
    assert "push failed: refused" in capsys.readouterr().err


def test_stale_key_survives_mark_seen_and_not_in_since(repo, monkeypatch):
    from the_nod import snapshot
    s = seed(repo); enable_push(repo)
    monkeypatch.setattr(GitSync, "pull_ff", lambda self: False)
    ctx = _ctx(repo)
    s.mark_seen("host-a", "2026-10-19T00:00:00")
    assert s.seen()["stale_since"] == ctx.stale_since
    state = snapshot.build(s, now="2026-10-20T10:00:00", host="host-b", since=None,
                           fresh=False, stale_since=ctx.stale_since)
    assert state["since"]["from"] != ctx.stale_since


def test_worktree_writes_go_to_main_tree(repo, worktree, capsys, monkeypatch):
    from the_nod.cli import main
    from tests.conftest import BRANCH, git
    assert main(["--root", str(repo), "init"]) == 0
    git(worktree, "merge", "--ff-only", BRANCH)  # the run worktree has its own copy of .nod
    assert (worktree / ".nod").is_dir()
    sub = worktree / "sub"
    sub.mkdir()
    capsys.readouterr()
    for cwd in (worktree, sub):
        monkeypatch.chdir(cwd)
        assert main(["card", "add", "X"]) == 0
        cid = capsys.readouterr().out.strip()
        assert list((repo / ".nod" / "cards").glob(f"{cid}-*.md"))
        assert not list((worktree / ".nod" / "cards").glob(f"{cid}-*.md"))
        assert git(repo, "log", "-1", "--format=%s").strip() == f"state: card add {cid}"


def test_root_in_worktree_is_refused(repo, worktree, capsys):
    from the_nod.cli import main
    from tests.conftest import BRANCH, git
    assert main(["--root", str(repo), "init"]) == 0
    git(worktree, "merge", "--ff-only", BRANCH)
    capsys.readouterr()
    assert main(["--root", str(worktree), "card", "add", "Y"]) == 2
    assert "the state must live in the main worktree" in capsys.readouterr().err
    assert not list((worktree / ".nod" / "cards").glob("*.md"))


def test_write_on_unborn_branch_makes_the_root_commit(tmp_path):
    from tests.conftest import git
    root = tmp_path / "tidepool"; root.mkdir()
    git(root, "init", "-q", "-b", "work")
    git(root, "config", "user.name", "owner"); git(root, "config", "user.email", "owner@example.com")
    (root / ".nod").mkdir()
    ctx = _ctx(root)
    assert ctx.fresh and ctx.sync.head() is None
    assert ctx.write("init", lambda: (root / ".nod" / "order.md").write_text("x", encoding="utf-8")) is True
    assert git(root, "log", "--format=%s").splitlines() == ["state: init"]
