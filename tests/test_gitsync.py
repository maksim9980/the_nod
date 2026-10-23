import subprocess, pytest
from the_nod.gitsync import GitSync, ProtectedBranch

def git(cwd, *a): return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8")

def test_commit_only_state_path(repo):
    (repo / ".nod").mkdir(); (repo / ".nod" / "order.md").write_text("# Порядок\n", encoding="utf-8")
    (repo / "other.txt").write_text("x")
    sha = GitSync(repo).commit("карточка c-1")
    assert sha and git(repo, "log", "-1", "--format=%s").stdout.strip() == "state: карточка c-1"
    assert "other.txt" in git(repo, "status", "--porcelain").stdout

def test_commit_nothing_returns_none(repo):
    assert GitSync(repo).commit("пусто") is None

def test_protected_branch(repo):
    git(repo, "checkout", "-b", "main")
    (repo / ".nod").mkdir(); (repo / ".nod" / "x").write_text("x")
    with pytest.raises(ProtectedBranch):
        GitSync(repo).commit("x")

def test_push_and_pull_ff(repo, tmp_path):
    (repo / ".nod").mkdir(); (repo / ".nod" / "x").write_text("x")
    s = GitSync(repo); s.commit("x"); assert s.push() is True
    clone = tmp_path / "clone"; git(tmp_path, "clone", "-b", "2026-10-20", str(tmp_path / "remote.git"), str(clone))
    assert (clone / ".nod" / "x").exists()
    (repo / ".nod" / "y").write_text("y"); s.commit("y"); s.push()
    assert GitSync(clone).pull_ff() is True and (clone / ".nod" / "y").exists()

def test_pull_ff_fails_on_divergence(repo, tmp_path):
    (repo / ".nod").mkdir(); (repo / ".nod" / "x").write_text("x")
    s = GitSync(repo); s.commit("x"); s.push()
    clone = tmp_path / "clone"; git(tmp_path, "clone", "-b", "2026-10-20", str(tmp_path / "remote.git"), str(clone))
    git(clone, "config", "user.email", "a@b"); git(clone, "config", "user.name", "a")
    (clone / ".nod" / "z").write_text("z"); GitSync(clone).commit("z")
    (repo / ".nod" / "y").write_text("y"); s.commit("y"); s.push()
    assert GitSync(clone).pull_ff() is False


def test_pull_ff_true_for_branch_missing_on_origin(repo, tmp_path):
    git(repo, "checkout", "-b", "2026-10-21")
    (repo / ".nod").mkdir(); (repo / ".nod" / "x").write_text("x")
    s = GitSync(repo)
    assert s.pull_ff() is True
    assert s.commit("x") and s.push() is True
    assert "2026-10-21" in git(tmp_path / "remote.git", "branch", "--list").stdout

def test_pull_ff_false_when_origin_unreachable(repo, tmp_path):
    git(repo, "remote", "set-url", "origin", str(tmp_path / "нет-такого.git"))
    s = GitSync(repo)
    assert s.pull_ff() is False and s.last_error

def test_missing_git_raises_giterror(repo, monkeypatch):
    from the_nod.gitsync import GitError
    def boom(*a, **k): raise FileNotFoundError("git")
    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(GitError, match="git not found"):
        GitSync(repo).branch()

def test_commit_excludes_local_files(repo):
    d = repo / ".nod"; d.mkdir()
    for name in ("order.md", "state.json", "seen.toml"):
        (d / name).write_text("x")
    GitSync(repo).commit("файлы")
    assert git(repo, "show", "--name-only", "--format=", "HEAD").stdout.split() == [".nod/order.md"]


def test_commit_with_gitignored_local_files(repo):
    from the_nod.gitsync import GitSync
    (repo / ".gitignore").write_text(".nod/state.json\n.nod/seen.toml\n", encoding="utf-8")
    state = repo / ".nod"
    state.mkdir()
    (state / "a.md").write_text("a\n", encoding="utf-8")
    (state / "state.json").write_text("{}", encoding="utf-8")
    assert GitSync(repo).commit("x") is not None

def test_commit_paths_only_given_paths(repo):
    (repo / "docs" / "briefs").mkdir(parents=True)
    (repo / "docs" / "briefs" / "a.md").write_text("a"); (repo / "other.txt").write_text("x")
    s = GitSync(repo)
    assert s.changed("docs/briefs") == ["docs/briefs/a.md"]
    assert s.commit_paths(["docs/briefs/a.md"], "docs(brief): a")
    assert git(repo, "log", "-1", "--format=%s").stdout.strip() == "docs(brief): a"
    assert s.changed("docs/briefs") == [] and "other.txt" in git(repo, "status", "--porcelain").stdout
    assert s.commit_paths(["docs/briefs/a.md"], "docs(brief): a") is None

def test_commit_paths_protected_branch(repo):
    git(repo, "checkout", "-b", "main"); (repo / "a.md").write_text("a")
    with pytest.raises(ProtectedBranch):
        GitSync(repo).commit_paths(["a.md"], "docs(brief): a")


def test_log_subjects_filters_by_since_and_path(repo):
    sync = GitSync(repo)
    (repo / ".nod").mkdir(); (repo / ".nod" / "order.md").write_text("x", encoding="utf-8")
    sync.commit("card add c-aaaa")
    (repo / "other.txt").write_text("y", encoding="utf-8"); git(repo, "add", "other.txt"); git(repo, "commit", "-m", "chore: other")
    assert sync.log_subjects("2000-01-01T00:00:00") == ["state: card add c-aaaa"]
    assert sync.log_subjects("2090-01-01T00:00:00") == []


# --- a branch without commits yet (a fresh `git init`) ---

@pytest.fixture
def unborn(tmp_path):
    """A repo after `git init -b work`: no commit, HEAD points at a branch that does not exist yet."""
    root = tmp_path / "tidepool"; root.mkdir()
    for args in (("init", "-q", "-b", "work"), ("config", "user.name", "owner"),
                 ("config", "user.email", "owner@example.com")):
        assert git(root, *args).returncode == 0
    return root

def test_unborn_branch_has_a_name_and_no_head(unborn):
    s = GitSync(unborn)
    assert s.branch() == "work" and s.head() is None
    assert git(unborn, "symbolic-ref", "-q", "HEAD").stdout.strip() == "refs/heads/work"

def test_unborn_main_is_protected(unborn):
    git(unborn, "symbolic-ref", "HEAD", "refs/heads/main")
    (unborn / ".nod").mkdir(); (unborn / ".nod" / "x").write_text("x")
    with pytest.raises(ProtectedBranch):
        GitSync(unborn).commit("x")

def test_detached_head_still_refused(repo):
    from the_nod.gitsync import GitError
    git(repo, "checkout", "-q", "--detach")
    with pytest.raises(GitError, match="detached HEAD"):
        GitSync(repo).branch()

def test_first_commit_on_unborn_branch_is_the_root(unborn):
    (unborn / ".nod").mkdir(); (unborn / ".nod" / "order.md").write_text("x", encoding="utf-8")
    (unborn / ".nod" / "state.json").write_text("{}", encoding="utf-8")
    s = GitSync(unborn)
    sha = s.commit("init")
    assert sha == s.head() and git(unborn, "rev-list", "--count", "HEAD").stdout.strip() == "1"
    assert git(unborn, "ls-tree", "-r", "--name-only", "HEAD").stdout.split() == [".nod/order.md"]

def test_undo_to_unborn_drops_the_root_commit_only(unborn):
    (unborn / "notes.md").write_text("staged by the owner", encoding="utf-8"); git(unborn, "add", "notes.md")
    (unborn / ".nod").mkdir(); (unborn / ".nod" / "state.json").write_text("{}", encoding="utf-8")
    s = GitSync(unborn)
    before = s.head()
    s.undo_last(before)  # nothing committed yet: nothing to undo
    assert before is None and s.head() is None
    (unborn / ".nod" / "driver.lock").write_text("lock", encoding="utf-8")
    assert s.commit("driver brief c-1") is not None
    s.undo_last(before)
    assert s.head() is None and s.branch() == "work"
    assert not (unborn / ".nod" / "driver.lock").exists() and (unborn / ".nod" / "state.json").exists()
    assert git(unborn, "status", "--porcelain", "--", "notes.md").stdout.startswith("A  notes.md")

def test_undo_to_unborn_refuses_a_second_commit(unborn):
    from the_nod.gitsync import GitError
    (unborn / ".nod").mkdir(); s = GitSync(unborn)
    (unborn / ".nod" / "a.md").write_text("a", encoding="utf-8"); s.commit("a")
    (unborn / ".nod" / "b.md").write_text("b", encoding="utf-8"); second = s.commit("b")
    with pytest.raises(GitError, match="not the first commit"):
        s.undo_last(None)
    assert s.head() == second

def test_undo_to_unborn_refuses_a_root_commit_beyond_the_state(unborn):
    """A root commit that also holds the owner's files (made by hand, or `nod` was not the one) is not dropped."""
    from the_nod.gitsync import GitError
    (unborn / ".nod").mkdir(); (unborn / ".nod" / "order.md").write_text("x", encoding="utf-8")
    (unborn / "notes.md").write_text("the owner's notes", encoding="utf-8")
    git(unborn, "add", "-A"); git(unborn, "commit", "-q", "-m", "first")
    s = GitSync(unborn)
    root = s.head()
    with pytest.raises(GitError, match="notes.md"):
        s.undo_last(None)
    assert s.head() == root and (unborn / "notes.md").exists()
    assert git(unborn, "ls-files").stdout.split() == [".nod/order.md", "notes.md"]

def test_undo_to_unborn_keeps_an_edit_made_after_the_commit(unborn):
    from the_nod.gitsync import GitError
    (unborn / ".nod").mkdir(); s = GitSync(unborn)
    lock_file = unborn / ".nod" / "driver.lock"
    lock_file.write_text("lock", encoding="utf-8"); sha = s.commit("lock")
    lock_file.write_text("edited after the commit", encoding="utf-8")
    with pytest.raises(GitError):
        s.undo_last(None)
    assert s.head() == sha and lock_file.read_text(encoding="utf-8") == "edited after the commit"
