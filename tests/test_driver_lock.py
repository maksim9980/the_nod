"""The driver lock: `driver.lock` through git, the local pid file, the heartbeat and the driver log."""
import subprocess, sys
from types import SimpleNamespace
from the_nod import context
from the_nod.driver import lock, log as driver_log
from the_nod.gitsync import GitSync
from the_nod.store import Store
from tests.conftest import BRANCH, enable_push, git

NOW = "2026-10-21T12:00:00"

def test_lock_state():
    assert lock.lock_state(None, "a", NOW) == "free"
    assert lock.lock_state({"host": "a", "at": "2026-10-21T11:59:00"}, "a", NOW) == "mine"
    assert lock.lock_state({"host": "b", "at": "2026-10-21T11:01:00"}, "a", NOW) == "foreign"
    assert lock.lock_state({"host": "b", "at": "2026-10-21T10:59:00"}, "a", NOW) == "abandoned"
    assert lock.lock_state({"host": "b", "at": "yesterday"}, "a", NOW) == "abandoned"
    assert lock.foreign_message({"host": "b", "at": NOW}) == f"work in progress on b since {NOW}"

def test_claim_writes_lock_with_change_in_one_commit(repo):
    from the_nod.cli import main
    assert main(["--root", str(repo), "init"]) == 0
    ctx = context.open(SimpleNamespace(root=str(repo)))
    assert lock.claim(ctx, "driver brief c-1", lambda: (repo / ".nod" / "x.md").write_text("x", encoding="utf-8")) is True
    assert ctx.store.lock()["host"] == ctx.host
    files = git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert ".nod/driver.lock" in files and ".nod/x.md" in files

def test_claim_rolls_back_when_push_fails(repo, monkeypatch):
    from the_nod.cli import main
    assert main(["--root", str(repo), "init"]) == 0
    enable_push(repo)
    ctx = context.open(SimpleNamespace(root=str(repo)))
    before = ctx.sync.head()
    monkeypatch.setattr(GitSync, "push", lambda self: setattr(self, "last_error", "refused") or False)
    assert lock.claim(ctx, "driver brief c-1", lambda: (repo / ".nod" / "x.md").write_text("x", encoding="utf-8")) is False
    assert ctx.sync.head() == before and ctx.store.lock() is None and not (repo / ".nod" / "x.md").exists()

def test_two_clones_only_one_wins(repo, tmp_path):
    from the_nod.cli import main
    assert main(["--root", str(repo), "init"]) == 0
    enable_push(repo); git(repo, "push", "-q", "origin", BRANCH)  # two machines share the state through origin
    other = tmp_path / "other"; git(tmp_path, "clone", "-b", "2026-10-20", str(tmp_path / "remote.git"), str(other))
    git(other, "config", "user.name", "o"); git(other, "config", "user.email", "o@o")
    a = context.open(SimpleNamespace(root=str(repo))); b = context.open(SimpleNamespace(root=str(other)))
    assert lock.claim(a, "driver brief c-1", lambda: None) is True
    assert lock.claim(b, "driver brief c-1", lambda: None) is False
    assert b.sync.pull_ff() is True and b.sync.head() == a.sync.head()

def test_process_lock_detects_live_pid(tmp_path):
    s = Store(tmp_path / ".nod")
    assert lock.process_lock(s) is None and (s.root / "driver" / "pid").read_text(encoding="utf-8").strip().isdigit()
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    (s.root / "driver" / "pid").write_text(str(other.pid), encoding="utf-8")
    try:
        assert lock.process_lock(s) == other.pid
    finally:
        other.kill(); other.wait()
    assert lock.process_lock(s) is None  # a dead pid: the file is rewritten with our own

def test_log_lines_and_rotation(tmp_path, capsys):
    path = tmp_path / "driver.log"; l = driver_log.Log(path, echo=True)
    l.info("start"); l.warn("lock")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].endswith(" INFO start") and lines[1].endswith(" WARN lock") and "start" in capsys.readouterr().out
    path.write_text("x" * (driver_log.ROTATE_BYTES + 1), encoding="utf-8"); l.error("after")
    assert (tmp_path / "driver.log.1").exists() and path.read_text(encoding="utf-8").endswith(" ERROR after\n")


def _init(repo):
    from the_nod.cli import main
    assert main(["--root", str(repo), "init"]) == 0


def test_claim_refuses_when_uncommitted_state_edits(repo):
    _init(repo)
    ctx = context.open(SimpleNamespace(root=str(repo)))
    before = ctx.sync.head()
    card = repo / ".nod" / "cards" / "x.md"
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text("an edit of someone else", encoding="utf-8")
    assert lock.claim(ctx, "driver brief c-1", lambda: None) is False
    assert ctx.sync.head() == before and card.exists() and ctx.store.lock() is None
    assert lock.last_refusal.startswith("dirty tree: ") and "x.md" in lock.last_refusal


def test_heartbeat_rolls_back_on_push_failure(repo, monkeypatch):
    _init(repo); enable_push(repo)
    ctx = context.open(SimpleNamespace(root=str(repo)))
    assert lock.claim(ctx, "driver brief c-1", lambda: None) is True
    before = ctx.sync.head()
    monkeypatch.setattr(GitSync, "push", lambda self: setattr(self, "last_error", "refused") or False)
    assert lock.heartbeat(ctx) is False
    assert ctx.sync.head() == before and lock.last_heartbeat == "push failed" and lock.last_refusal == ""


def test_heartbeat_ignores_foreign_lock(repo):
    _init(repo); enable_push(repo)
    ctx = context.open(SimpleNamespace(root=str(repo)))
    assert lock.claim(ctx, "driver brief c-1", lambda: ctx.store.write_lock("other-host", ctx.now)) is True
    ctx.store.write_lock("other-host", ctx.now)
    git(repo, "add", "-A", ".nod"); git(repo, "commit", "-m", "foreign"); git(repo, "push", "origin", "2026-10-20")
    before = ctx.sync.head()
    assert lock.heartbeat(ctx) is False
    assert ctx.sync.head() == before and ctx.store.lock()["host"] == "other-host"
    assert lock.last_heartbeat == "foreign lock"


def test_heartbeat_leaves_dirty_tree_alone(repo):
    _init(repo)
    ctx = context.open(SimpleNamespace(root=str(repo)))
    assert lock.claim(ctx, "driver brief c-1", lambda: None) is True and lock.last_refusal == ""
    before = ctx.sync.head()
    card = repo / ".nod" / "cards" / "x.md"
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text("an edit of someone else", encoding="utf-8")
    assert lock.heartbeat(ctx) is False
    assert ctx.sync.head() == before and card.exists() and "x.md" in lock.last_heartbeat

def test_claim_refuses_card_hidden_by_gitignore(repo):
    from the_nod.cli import main
    assert main(["--root", str(repo), "init"]) == 0
    cards = repo / ".nod" / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    (cards / ".gitignore").write_text("*\n", encoding="utf-8")
    (cards / "c-zzzz-agent.md").write_text("+++\nid = \"c-zzzz\"\n+++\n", encoding="utf-8")
    ctx = context.open(SimpleNamespace(root=str(repo)))
    assert git(repo, "status", "--porcelain", "--", ".nod/cards").strip() == ""  # git says nothing
    assert lock.claim(ctx, "driver brief c-1", lambda: None) is False
    assert lock.last_refusal.startswith("dirty tree:") and "c-zzzz-agent.md" in lock.last_refusal


def _unborn(tmp_path):
    """A fresh `git init -b work` with an empty `.nod/`: no commit yet, `head()` is `None`."""
    root = tmp_path / "tidepool"; root.mkdir()
    git(root, "init", "-q", "-b", "work")
    git(root, "config", "user.name", "owner"); git(root, "config", "user.email", "owner@example.com")
    (root / ".nod").mkdir()
    return root


def test_claim_on_unborn_branch_takes_the_lock_in_the_root_commit(tmp_path):
    root = _unborn(tmp_path)
    ctx = context.open(SimpleNamespace(root=str(root)))
    assert ctx.sync.head() is None
    assert lock.claim(ctx, "driver brief c-1", lambda: (root / ".nod" / "x.md").write_text("x", encoding="utf-8")) is True
    assert git(root, "rev-list", "--count", "HEAD").strip() == "1" and ctx.store.lock()["host"] == ctx.host


def test_claim_on_unborn_branch_rolls_back_to_no_commit(tmp_path, monkeypatch):
    root = _unborn(tmp_path)
    ctx = context.open(SimpleNamespace(root=str(root)))
    monkeypatch.setattr(GitSync, "push", lambda self: setattr(self, "last_error", "refused") or False)
    assert lock.claim(ctx, "driver brief c-1", lambda: (root / ".nod" / "x.md").write_text("x", encoding="utf-8")) is False
    assert lock.last_refusal == "push failed"
    assert ctx.sync.head() is None and ctx.sync.branch() == "work"
    assert not (root / ".nod" / "x.md").exists() and ctx.store.lock() is None
