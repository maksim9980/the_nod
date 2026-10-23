import json
from the_nod.cli import main
from tests.conftest import enable_push
from tests.test_snapshot import seed

def test_status_json_and_state_file(tmp_path, capsys):
    s = seed(tmp_path)
    assert main(["--root", str(s.root), "--json", "status", "--no-sync", "--since", "2026-10-17T00:00:00"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["waiting"][0]["id"] == "d-1111"
    assert (s.root / "state.json").exists()

def test_status_text_has_sections(tmp_path, capsys):
    s = seed(tmp_path)
    main(["--root", str(s.root), "status", "--no-sync"])
    out = capsys.readouterr().out
    assert "Waiting for you" in out and "In a run" in out and "Backlog" in out


def test_status_text_in_russian(tmp_path, capsys, monkeypatch):
    s = seed(tmp_path)
    monkeypatch.setenv("NOD_LANG", "ru")
    main(["--root", str(s.root), "status", "--no-sync"])
    out = capsys.readouterr().out
    assert "Ждёт тебя · 1" in out and "В ране · 1" in out and "Бэклог · 2" in out and "шаг 2: Шаг 2" in out

def test_broken_file_reports_path_and_line(tmp_path, capsys):
    s = seed(tmp_path)
    p = next((s.root / "cards").glob("c-aaaa-*.md")); p.write_text('+++\nid = "c-aaaa\n+++\n', encoding="utf-8")
    assert main(["--root", str(s.root), "status", "--no-sync"]) == 2
    assert f"{p}:2" in capsys.readouterr().err


def test_root_as_repo_root_equals_state_dir(repo, capsys):
    s = seed(repo)
    args = ["--json", "status", "--no-sync", "--since", "2026-10-17T00:00:00"]
    assert main(["--root", str(s.root), *args]) == 0
    by_state = json.loads(capsys.readouterr().out)
    assert main(["--root", str(repo), *args]) == 0
    by_repo = json.loads(capsys.readouterr().out)
    for state in (by_state, by_repo):
        state.pop("generated_at")
    assert by_state == by_repo

def test_root_without_state_dir_fails(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "status", "--no-sync"]) == 2
    assert "no state" in capsys.readouterr().err

def test_load_error_without_line_has_no_colon(tmp_path, capsys):
    s = seed(tmp_path)
    p = next((s.root / "cards").glob("c-bbbb-*.md"))
    p.write_text(p.read_text(encoding="utf-8").replace('status = "backlog"', 'status = "bogus"'), encoding="utf-8")
    assert main(["--root", str(s.root), "status", "--no-sync"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ") and err.rstrip().endswith(f"({p})")

def test_status_marks_host_seen(tmp_path):
    from the_nod.paths import host_name
    s = seed(tmp_path)
    assert main(["--root", str(s.root), "status", "--no-sync"]) == 0
    assert host_name() in s.seen()


def test_status_marks_stale_when_pull_fails(repo, tmp_path, capsys, monkeypatch):
    from the_nod.cli import main
    from the_nod import gitsync
    seed(repo); enable_push(repo)  # puts .nod at the root of repo
    monkeypatch.setattr(gitsync.GitSync, "pull_ff", lambda self: False)
    assert main(["--root", str(repo), "--json", "status"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["fresh"] is False and out["stale_since"]


def test_no_sync_does_not_pull(repo, monkeypatch):
    from the_nod import gitsync
    seed(repo); enable_push(repo)
    calls = []
    monkeypatch.setattr(gitsync.GitSync, "pull_ff", lambda self: calls.append(1) or True)
    assert main(["--root", str(repo), "status", "--no-sync"]) == 0
    assert calls == []


def test_giterror_during_pull_makes_stale_not_crash(repo, capsys, monkeypatch):
    from the_nod import gitsync
    seed(repo); enable_push(repo)
    def boom(self): raise gitsync.GitError("failure")
    monkeypatch.setattr(gitsync.GitSync, "pull_ff", boom)
    assert main(["--root", str(repo), "--json", "status"]) == 0
    assert json.loads(capsys.readouterr().out)["fresh"] is False


def test_main_maps_stale_to_exit_3(repo, capsys, monkeypatch):
    from the_nod.commands import status
    from the_nod.context import Stale
    def refuse(args): raise Stale("the state has been stale since X: run git pull first")
    monkeypatch.setattr(status, "run", refuse)
    assert main(["--root", str(repo), "status"]) == 3
    assert capsys.readouterr().err.startswith("error: the state has been stale")


def test_main_reports_missing_git(repo, capsys, monkeypatch):
    from the_nod.commands import status
    from the_nod.gitsync import GitError
    def nogit(args): raise GitError("git not found")
    monkeypatch.setattr(status, "run", nogit)
    assert main(["--root", str(repo), "status"]) == 2
    assert "error: git not found" in capsys.readouterr().err


def test_status_text_says_stale_first(repo, capsys, monkeypatch):
    from the_nod import gitsync
    seed(repo); enable_push(repo)
    monkeypatch.setattr(gitsync.GitSync, "pull_ff", lambda self: False)
    assert main(["--root", str(repo), "status"]) == 0
    first = capsys.readouterr().out.splitlines()[0]
    assert first.startswith("The state has been stale since ")
    assert first.endswith("writes are off, run git pull first")


def test_status_text_says_stale_first_in_russian(repo, capsys, monkeypatch):
    from the_nod import gitsync
    seed(repo); enable_push(repo)
    monkeypatch.setattr(gitsync.GitSync, "pull_ff", lambda self: False)
    monkeypatch.setenv("NOD_LANG", "ru")
    assert main(["--root", str(repo), "status"]) == 0
    first = capsys.readouterr().out.splitlines()[0]
    assert first.startswith("Состояние не свежее с ") and first.endswith("записи отключены, сначала git pull")


def test_json_status_does_not_mark_seen(tmp_path, capsys):
    from the_nod.paths import host_name
    s = seed(tmp_path)
    assert main(["--root", str(s.root), "--json", "status", "--no-sync"]) == 0
    assert host_name() not in s.seen()


def test_peek_does_not_mark_seen(tmp_path, capsys):
    from the_nod.paths import host_name
    s = seed(tmp_path)
    assert main(["--root", str(s.root), "status", "--no-sync", "--peek"]) == 0
    assert host_name() not in s.seen()
    assert main(["--root", str(s.root), "status", "--no-sync"]) == 0
    assert host_name() in s.seen()


def test_json_flag_after_subcommand(tmp_path, capsys):
    s = seed(tmp_path)
    assert main(["--root", str(s.root), "status", "--json", "--no-sync"]) == 0
    assert json.loads(capsys.readouterr().out)["waiting"][0]["id"] == "d-1111"
    assert main(["--root", str(s.root), "card", "show", "c-aaaa", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "c-aaaa"
    assert main(["--root", str(s.root), "status", "--no-sync"]) == 0
    assert not capsys.readouterr().out.startswith("{")
