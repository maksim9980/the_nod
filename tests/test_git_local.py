"""Decision R6: the state stays local unless `[git] push = true`; `nod init` refuses a protected branch."""
import hashlib
import re
import subprocess
from types import SimpleNamespace

import pytest

from the_nod import context, harness, model as m
from the_nod.cli import main
from the_nod.driver import files, guard, lock
from the_nod.gitsync import GitSync
from the_nod.store import Store
from tests.conftest import BRANCH, enable_push, git
from tests.driver_helpers import add_card, driver_run, env_for_tests, fake, setup

WORK = "2026-10-21"
CYRILLIC = re.compile(r"[Ѐ-ӿ]")
# Every git command that may reach a remote, plus `git remote` that decides whether there is one.
NETWORK = {"fetch", "pull", "push", "ls-remote", "remote"}
GIT_COMMENT = ("# false: Nod never talks to a remote. true: pull before every write and push after it"
               " — needed when the driver and you work from two machines.")
REFUSAL = ('error: branch "{branch}" is protected: Nod commits its state on a work branch'
           " — create one with git switch -c <name>, then run nod init again")


def _record_git(monkeypatch) -> list[tuple[str, ...]]:
    """Every argument list `GitSync` passes to git, in order."""
    calls: list[tuple[str, ...]] = []
    real = GitSync._git

    def spy(self, *args):
        calls.append(args)
        return real(self, *args)

    monkeypatch.setattr(GitSync, "_git", spy)
    return calls


def _network(calls) -> list[tuple[str, ...]]:
    return [args for args in calls if NETWORK & set(args)]


def _origin_sha(repo, branch: str) -> str:
    """The sha of `branch` in the bare origin, empty when origin has no such branch."""
    out = git(repo.parent / "remote.git", "for-each-ref", "--format=%(objectname)", f"refs/heads/{branch}")
    return out.strip()


def _init(repo, capsys) -> None:
    assert main(["--root", str(repo), "init"]) == 0
    capsys.readouterr()


def _card_add(repo, capsys, title: str = "Export habits to CSV") -> tuple[int, str, str]:
    code = main(["--root", str(repo), "card", "add", title])
    out = capsys.readouterr()
    return code, out.out.strip(), out.err


def test_default_manifest_is_local_only(repo, capsys):
    assert main(["--root", str(repo), "init"]) == 0
    lines = (repo / ".nod" / "harness.toml").read_text(encoding="utf-8").splitlines()
    assert "[git]" in lines and "push = false" in lines and GIT_COMMENT in lines
    assert harness.load(Store(repo / ".nod")).push is False
    assert harness.read_push(repo / ".nod") is False


def test_russian_template_keeps_the_git_table(repo, capsys, monkeypatch):
    monkeypatch.setenv("NOD_LANG", "ru")
    assert main(["--root", str(repo), "init"]) == 0
    lines = (repo / ".nod" / "harness.toml").read_text(encoding="utf-8").splitlines()
    git_at = lines.index("[git]")
    comment = lines[git_at + 1]
    assert comment.startswith("# false") and CYRILLIC.search(comment) and lines[git_at + 2] == "push = false"
    assert harness.load(Store(repo / ".nod")).push is False


def test_write_does_not_push_by_default(repo, capsys, monkeypatch):
    initial = _origin_sha(repo, BRANCH)
    calls = _record_git(monkeypatch)
    _init(repo, capsys)
    git(repo, "switch", "-c", WORK)
    code, cid, err = _card_add(repo, capsys)
    assert code == 0 and cid.startswith("c-") and err == ""
    assert git(repo, "log", "-1", "--format=%s").strip() == f"state: card add {cid}"
    assert _origin_sha(repo, WORK) == "" and _origin_sha(repo, BRANCH) == initial
    assert calls and _network(calls) == []


def test_no_pull_when_local(repo, tmp_path, capsys):
    _init(repo, capsys)
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", "-b", BRANCH, str(tmp_path / "remote.git"), str(other))
    git(other, "config", "user.name", "o"); git(other, "config", "user.email", "o@example.com")
    (other / "notes.md").write_text("from desktop\n", encoding="utf-8")
    git(other, "add", "notes.md"); git(other, "commit", "-q", "-m", "foreign")
    git(other, "push", "-q", "origin", BRANCH)
    foreign = git(other, "rev-parse", "HEAD").strip()
    tracking = git(repo, "rev-parse", f"origin/{BRANCH}").strip()
    code, cid, _ = _card_add(repo, capsys)
    assert code == 0 and cid.startswith("c-")
    ctx = context.open(SimpleNamespace(root=str(repo)))
    assert ctx.fresh and "stale_since" not in ctx.store.seen()
    # Nothing was fetched: the foreign commit is unknown here and origin/<branch> did not move.
    known = subprocess.run(["git", "cat-file", "-e", foreign], cwd=repo, capture_output=True)
    assert known.returncode != 0 and git(repo, "rev-parse", f"origin/{BRANCH}").strip() == tracking
    # The same history with push on: the pull fails on the divergence and the write is refused.
    enable_push(repo)
    code, _, err = _card_add(repo, capsys, "Weekly email digest")
    assert code == 3 and "has been stale" in err


def test_push_true_pushes(repo, capsys):
    _init(repo, capsys)
    git(repo, "switch", "-c", WORK)
    enable_push(repo)
    assert harness.read_push(repo / ".nod") is True
    assert _origin_sha(repo, WORK) == ""
    code, cid, _ = _card_add(repo, capsys)
    assert code == 0 and cid.startswith("c-")
    assert _origin_sha(repo, WORK) == git(repo, "rev-parse", "HEAD").strip()


def test_lock_claimed_without_remote_when_local(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys, push=False)
    git(repo, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    cid = add_card(repo, capsys)
    calls = _record_git(monkeypatch)
    code, out, _ = driver_run(repo, "once", capsys=capsys)
    assert code == 0 and out.strip() == f"brief: brief {cid}"
    assert calls and _network(calls) == []
    subjects = git(repo, "log", "--format=%s").splitlines()
    claim = f"state: driver brief {cid} briefing"
    assert claim in subjects
    sha = git(repo, "log", "--format=%H", "--fixed-strings", f"--grep={claim}").split()[0]
    assert ".nod/driver.lock" in git(repo, "show", "--name-only", "--format=", sha).split()
    assert s.lock() is not None and s.lock()["host"] == context.host_name()


def test_lock_not_claimed_with_push_and_unreachable_origin(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys, push=True)
    add_card(repo, capsys)
    git(repo, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    code, out, _ = driver_run(repo, "once", capsys=capsys)
    assert code == 3 and out.startswith("stale: ")
    assert s.lock() is None


def test_guard_reference_without_fetch_when_local(repo, capsys, monkeypatch):
    assert main(["--root", str(repo), "init"]) == 0
    calls = _record_git(monkeypatch)
    ctx = context.open(SimpleNamespace(root=str(repo)))
    ref = guard.snapshot(ctx)
    manifest = repo / ".nod" / "harness.toml"
    assert ref.remote is None and ref.sha == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert _network(calls) == []
    original = manifest.read_text(encoding="utf-8")
    manifest.write_text(original + "# the agent was here\n", encoding="utf-8")
    assert guard.restore_manifest(ctx, ref) == guard.MANIFEST_LOCAL
    assert manifest.read_text(encoding="utf-8") == original
    assert _network(calls) == []


def test_heartbeat_and_reopen_keep_the_local_mode_of_the_pass(repo, capsys, monkeypatch):
    _init(repo, capsys)
    ctx = context.open(SimpleNamespace(root=str(repo)))
    assert ctx.remote is False and lock.claim(ctx, "driver brief c-1", lambda: None) is True
    # The agent's command turns push on and commits the manifest (the guard restores it only afterwards).
    manifest = repo / ".nod" / "harness.toml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace("push = false", "push = true"),
                        encoding="utf-8")
    git(repo, "commit", "-q", "-am", "agent turns push on")
    origin = _origin_sha(repo, BRANCH)
    calls = _record_git(monkeypatch)
    assert lock.heartbeat(ctx) is True, lock.last_heartbeat
    assert files.reopen(ctx).remote is False
    assert _network(calls) == [] and _origin_sha(repo, BRANCH) == origin
    # A new pass reads the committed manifest again.
    assert context.open(SimpleNamespace(root=str(repo))).remote is True


def test_git_sync_without_remote_never_calls_git_for_the_network(repo, monkeypatch):
    calls = _record_git(monkeypatch)
    sync = GitSync(repo, remote=False)
    assert sync.has_remote() is False
    assert sync.pull_ff() is True and sync.push() is True
    assert sync.remote_file(".nod/harness.toml") is None
    assert _network(calls) == []


def test_git_table_rejects_unknown_key():
    with pytest.raises(harness.HarnessError, match="remote"):
        harness.validate({"git": {"remote": "x"}})


@pytest.mark.parametrize("data, message", [
    ({"git": {"push": "yes"}}, "push"),
    ({"git": {"push": 1}}, "push"),
    ({"git": "push"}, "git"),
])
def test_git_table_checks_its_values(data, message):
    with pytest.raises(harness.HarnessError, match=message):
        harness.validate(data)


def test_git_table_values():
    assert harness.validate({}).push is False
    assert harness.validate({"git": {}}).push is False
    assert harness.validate({"git": {"push": True}}).push is True


def test_read_push(tmp_path):
    state = tmp_path / ".nod"
    state.mkdir()
    assert harness.read_push(state) is False
    manifest = state / "harness.toml"
    for text, expected in (('adapter = "default"\n', False), ("[git]\npush = false\n", False),
                           ("[git]\npush = true\n", True), ("[git\n", False)):
        manifest.write_text(text, encoding="utf-8")
        assert harness.read_push(state) is expected, text
    for bad in ('[git]\npush = "true"\n', '[git]\nremote = "x"\n', 'git = 1\n'):
        manifest.write_text(bad, encoding="utf-8")
        with pytest.raises(harness.HarnessError):
            harness.read_push(state)


def _project(tmp_path, branch: str, *, commit: bool = True):
    """The owner's Tidepool repo on `branch`; `commit=False` is a fresh `git init` without any commit."""
    root = tmp_path / "tidepool"
    root.mkdir()
    git(root, "init", "-q", "-b", branch)
    git(root, "config", "user.name", "owner"); git(root, "config", "user.email", "owner@example.com")
    if commit:
        (root / "README.md").write_text("# Tidepool\n", encoding="utf-8")
        git(root, "add", "README.md"); git(root, "commit", "-q", "-m", "first")
    return root


@pytest.mark.parametrize("branch", ["main", "master"])
def test_init_on_main_refuses_before_creating_anything(tmp_path, capsys, monkeypatch, branch):
    root = _project(tmp_path, branch)
    head = git(root, "rev-parse", "HEAD").strip()
    monkeypatch.chdir(root)
    assert main(["init"]) == 3
    assert capsys.readouterr().err.strip() == REFUSAL.format(branch=branch)
    assert not (root / ".nod").exists() and not (root / ".gitignore").exists()
    assert git(root, "rev-parse", "HEAD").strip() == head


def test_init_on_main_refuses_in_russian(tmp_path, capsys, monkeypatch):
    root = _project(tmp_path, "main")
    monkeypatch.setenv("NOD_LANG", "ru")
    assert main(["--root", str(root), "init"]) == 3
    err = capsys.readouterr().err
    assert "«main»" in err and "git switch -c" in err and "nod init" in err
    assert not (root / ".nod").exists()


def test_init_on_detached_head_refuses_before_creating_anything(tmp_path, capsys):
    root = _project(tmp_path, "work")
    git(root, "checkout", "-q", "--detach")
    assert main(["--root", str(root), "init"]) == 2
    assert "not on a branch: detached HEAD" in capsys.readouterr().err
    assert not (root / ".nod").exists() and not (root / ".gitignore").exists()


def test_init_on_work_branch_after_switch(tmp_path, capsys):
    root = _project(tmp_path, "main")
    assert main(["--root", str(root), "init"]) == 3
    git(root, "switch", "-q", "-c", "tidepool-work")
    capsys.readouterr()
    assert main(["--root", str(root), "init"]) == 0
    assert (root / ".nod" / "harness.toml").exists()
    assert git(root, "log", "-1", "--format=%s").strip() == "state: init"


# --- a fresh `git init` without commits: the quick start ---

def test_init_on_unborn_work_branch_makes_the_root_commit(tmp_path, capsys, monkeypatch):
    root = _project(tmp_path, "work", commit=False)
    monkeypatch.chdir(root)
    assert main(["init"]) == 0
    assert capsys.readouterr().err == ""
    assert git(root, "rev-list", "--count", "HEAD").strip() == "1"
    assert git(root, "log", "--format=%s").splitlines() == ["state: init"]
    assert ".nod/harness.toml" in git(root, "ls-tree", "-r", "--name-only", "HEAD").split()


@pytest.mark.parametrize("branch", ["main", "master"])
def test_init_on_unborn_main_refuses_then_works_after_switch(tmp_path, capsys, monkeypatch, branch):
    root = _project(tmp_path, branch, commit=False)
    monkeypatch.chdir(root)
    assert main(["init"]) == 3
    assert capsys.readouterr().err.strip() == REFUSAL.format(branch=branch)
    assert not (root / ".nod").exists() and not (root / ".gitignore").exists()
    git(root, "switch", "-q", "-c", "work")  # what the refusal says to do
    assert main(["init"]) == 0
    assert git(root, "log", "--format=%s").splitlines() == ["state: init"]


def test_driver_once_when_the_only_commit_is_init(tmp_path, capsys, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    root = _project(tmp_path, "work", commit=False)
    store = Store(root / ".nod")
    commands = "\n".join(f"{kind} = '{fake(mode)}'" for kind, mode in
                         (("brief", "brief-ok"), ("run", "run-ok"), ("accept", "accept-ok")))
    (store.root / "harness.toml").write_text(
        f'adapter = "default"\ndriver_host = ""\n[commands]\n{commands}\n[git]\npush = false\n', encoding="utf-8")
    store.save_card(m.Card(id="c-aaaa", title="Export habits to CSV", status="backlog",
                           created="2026-10-21T10:00:00", source="owner"))
    store.set_order(["c-aaaa"])
    assert main(["--root", str(root), "init"]) == 0
    capsys.readouterr()
    root_sha = git(root, "rev-parse", "HEAD").strip()
    assert git(root, "log", "--format=%s").splitlines() == ["state: init"]
    code, out, _ = driver_run(root, "once", capsys=capsys)
    assert code == 0 and out.strip() == "brief: brief c-aaaa"
    claim = git(root, "log", "--format=%H %P %s", "--fixed-strings", "--grep=driver brief c-aaaa briefing").split()
    assert claim[1] == root_sha  # the lock commit sits right on top of the root commit
    assert store.lock() is not None


# --- a manifest that does not read: say that Nod went local ---

BROKEN = "[git\npush = true\n"


def test_broken_manifest_warns_once_and_stays_local(repo, capsys, monkeypatch):
    _init(repo, capsys)
    enable_push(repo)
    _card_add(repo, capsys)  # pushes: the project syncs with origin
    origin = _origin_sha(repo, BRANCH)
    assert origin == git(repo, "rev-parse", "HEAD").strip()
    (repo / ".nod" / "harness.toml").write_text(BROKEN, encoding="utf-8")
    calls = _record_git(monkeypatch)
    code, cid, err = _card_add(repo, capsys, "Weekly email digest")
    lines = err.splitlines()
    assert code == 0 and cid.startswith("c-") and len(lines) == 1
    assert lines[0].startswith("warning: cannot read the manifest ") and lines[0].endswith(
        "Nod stays local, no pull or push, until it is fixed")
    assert _network(calls) == [] and _origin_sha(repo, BRANCH) == origin


def test_broken_manifest_warning_in_russian(repo, capsys, monkeypatch):
    _init(repo, capsys)
    (repo / ".nod" / "harness.toml").write_text(BROKEN, encoding="utf-8")
    monkeypatch.setenv("NOD_LANG", "ru")
    _, _, err = _card_add(repo, capsys)
    lines = err.splitlines()
    assert len(lines) == 1 and lines[0].startswith("предупреждение: манифест ")
    assert lines[0].endswith("Nod работает локально, без pull и push, пока его не исправят")


def test_read_push_warns_only_for_a_manifest_that_does_not_read(tmp_path, capsys):
    state = tmp_path / ".nod"
    state.mkdir()
    assert harness.read_push(state) is False and capsys.readouterr().err == ""
    (state / "harness.toml").write_text("[git]\npush = true\n", encoding="utf-8")
    assert harness.read_push(state) is True and capsys.readouterr().err == ""
    (state / "harness.toml").write_text(BROKEN, encoding="utf-8")
    assert harness.read_push(state) is False
    assert len(capsys.readouterr().err.splitlines()) == 1
    (state / "harness.toml").write_bytes(b"\xff\xfe[git]")
    assert harness.read_push(state) is False
    assert capsys.readouterr().err.startswith("warning: cannot read the manifest ")
