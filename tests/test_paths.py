import pytest

from the_nod import paths


def test_find_state_dir_walks_up(tmp_path):
    (tmp_path / ".nod").mkdir()
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert paths.find_state_dir(deep) == tmp_path / ".nod"


def test_find_state_dir_none(tmp_path):
    assert paths.find_state_dir(tmp_path) is None


def test_main_root_from_worktree(repo, worktree):
    assert paths.main_worktree_root(worktree) == repo.resolve()


def test_main_root_from_subdir(repo):
    sub = repo / "x"
    sub.mkdir()
    assert paths.main_worktree_root(sub) == repo.resolve()


def test_not_a_repo(tmp_path):
    with pytest.raises(paths.NotARepo):
        paths.main_worktree_root(tmp_path)
