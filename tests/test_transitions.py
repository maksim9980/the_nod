import subprocess
from types import SimpleNamespace
from the_nod import context, transitions as tr
from the_nod.cli import main
from the_nod.gitsync import GitSync
from the_nod.model import DECISION_KINDS, Step
from the_nod.store import Store

def run(repo, *args, capsys):
    code = main(["--root", str(repo), *args]); out = capsys.readouterr(); return code, out.out, out.err

def seeded(repo, capsys):
    run(repo, "init", capsys=capsys)
    cid = run(repo, "card", "add", "Экспорт", capsys=capsys)[1].strip()
    s = Store(repo / ".nod"); c = s.load_card(cid); c.steps = [Step(1, "Таблица"), Step(2, "Статус")]; s.save_card(c)
    return cid, s

def test_progress_updates_contracts_and_keeps_running(repo, capsys):
    cid, s = seeded(repo, capsys)
    rid = run(repo, "run", "start", cid, "--step", "1", "--contracts", "3", capsys=capsys)[1].strip()
    assert run(repo, "run", "progress", rid, "--contracts-done", "2", capsys=capsys)[0] == 0
    r = s.load_run(rid); assert r.contracts_done == 2 and r.finished is None and "contracts done: 2" in r.body
    assert s.load_card(cid).status == "running"
    assert subprocess.run(["git", "log", "-1", "--format=%s"], cwd=repo, capture_output=True, text=True, encoding="utf-8").stdout.strip() == f"state: run progress {rid} 2"

def test_progress_on_finished_run_refused(repo, capsys):
    cid, s = seeded(repo, capsys)
    rid = run(repo, "run", "start", cid, "--step", "1", capsys=capsys)[1].strip()
    run(repo, "run", "finish", rid, "--result", "ok", capsys=capsys)
    code, _, err = run(repo, "run", "progress", rid, "--contracts-done", "1", capsys=capsys)
    assert code == 2 and "already finished" in err

def test_finish_keeps_progress_lines_in_body(repo, capsys):
    cid, s = seeded(repo, capsys)
    rid = run(repo, "run", "start", cid, "--step", "1", capsys=capsys)[1].strip()
    run(repo, "run", "progress", rid, "--contracts-done", "1", capsys=capsys)
    run(repo, "run", "finish", rid, "--result", "stop", "--note", "завис", capsys=capsys)
    body = s.load_run(rid).body
    assert "contracts done: 1" in body and body.endswith("\nзавис")

def test_start_run_function_matches_cli_checks(repo, capsys):
    cid, s = seeded(repo, capsys)
    card = s.load_card(cid)
    r, apply = tr.start_run(s, card, step=2, contracts=4, now="2026-10-21T10:00:00"); apply()
    assert s.load_run(r.id).step == 2 and s.load_card(cid).status == "running"
    import pytest
    with pytest.raises(context.CliError, match="a run is already open"):
        tr.start_run(s, s.load_card(cid), step=1, contracts=0, now="2026-10-21T10:01:00")

def test_make_decision_rejects_unknown_kind(tmp_path):
    import pytest
    s = Store(tmp_path / ".nod")
    with pytest.raises(context.CliError, match='unknown kind "x"'):
        tr.make_decision(s, kind="x", question="Q", proposed="A", options=["A"], now="2026-10-21T10:00:00")
    assert "pain" in DECISION_KINDS

def test_write_returns_pushed(repo, monkeypatch):
    from tests.conftest import enable_push
    (repo / ".nod").mkdir(); enable_push(repo)
    run_ok = context.open(SimpleNamespace(root=str(repo)))
    assert run_ok.write("a", lambda: (repo / ".nod" / "a.md").write_text("a", encoding="utf-8")) is True
    monkeypatch.setattr(GitSync, "push", lambda self: setattr(self, "last_error", "refused") or False)
    ctx = context.open(SimpleNamespace(root=str(repo)))
    assert ctx.write("b", lambda: (repo / ".nod" / "b.md").write_text("b", encoding="utf-8")) is False

def test_undo_last_restores_head_and_tree(repo):
    s = GitSync(repo); (repo / ".nod").mkdir(); (repo / "free.txt").write_text("free", encoding="utf-8")
    before = s.head()
    (repo / ".nod" / "x.md").write_text("x", encoding="utf-8"); s.commit("x")
    s.undo_last(before)
    assert s.head() == before and not (repo / ".nod" / "x.md").exists() and (repo / "free.txt").read_text(encoding="utf-8") == "free"

def test_driver_files_are_local(repo, capsys):
    run(repo, "init", capsys=capsys)
    d = repo / ".nod" / "driver"; d.mkdir(); (d / "r.toml").write_text("x", encoding="utf-8")
    (repo / ".nod" / "driver.log").write_text("log", encoding="utf-8")
    run(repo, "card", "add", "A", capsys=capsys)
    files = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=repo, capture_output=True, text=True, encoding="utf-8").stdout
    assert "driver" not in files
    assert ".nod/driver/" in (repo / ".gitignore").read_text(encoding="utf-8")

def test_accept_error_order_result_before_captions(repo, capsys):
    cid, _ = seeded(repo, capsys)
    code, _, err = run(repo, "accept", cid, "--level", "1", "--result", "xyz", "--frame", "a.png", capsys=capsys)
    assert code == 2 and 'unknown result "xyz"' in err

def abandon(s, cid, status):
    """An old state: the card left `running` but its run stayed open (the old `card return` left it open)."""
    card = s.load_card(cid); card.status = status; s.save_card(card)

def commits(repo):
    return int(subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=repo, capture_output=True, text=True, encoding="utf-8").stdout)

def test_start_run_closes_the_abandoned_run_in_its_own_apply(repo, capsys):
    import pytest
    cid, s = seeded(repo, capsys)
    for status in ("returned", "ready", "briefing", "backlog", "accepting"):
        old = run(repo, "run", "start", cid, "--step", "1", capsys=capsys)[1].strip()
        abandon(s, cid, status)
        new, apply = tr.start_run(s, s.load_card(cid), step=1, contracts=0, now="2026-10-21T10:05:00")
        assert s.load_run(old).finished is None  # nothing is written before `apply`
        apply()
        closed = s.load_run(old)
        assert closed.finished == "2026-10-21T10:05:00" and closed.result == "stop", status
        assert closed.body == f"closed when run {new.id} started: the card was not running"
        assert s.load_run(new.id).finished is None and s.load_card(cid).status == "running"
        assert [r.id for r in s.runs() if r.finished is None] == [new.id]
        with pytest.raises(context.CliError, match="a run is already open"):  # a running card still refuses
            tr.start_run(s, s.load_card(cid), step=1, contracts=0, now="2026-10-21T10:06:00")
        run(repo, "run", "finish", new.id, "--result", "stop", capsys=capsys)

def test_run_start_command_closes_the_abandoned_run_in_both_languages(repo, capsys, monkeypatch):
    cid, s = seeded(repo, capsys)
    old = run(repo, "run", "start", cid, "--step", "1", capsys=capsys)[1].strip()
    abandon(s, cid, "returned")
    before = commits(repo)
    code, out, _ = run(repo, "run", "start", cid, "--step", "1", capsys=capsys)
    new = out.strip()
    assert code == 0 and s.load_run(old).result == "stop" and new in s.load_run(old).body
    assert commits(repo) == before + 1  # the closing and the start are one commit
    abandon(s, cid, "ready")
    monkeypatch.setenv("NOD_LANG", "ru")
    newer = run(repo, "run", "start", cid, "--step", "1", capsys=capsys)[1].strip()
    assert s.load_run(new).body == f"закрыт при старте рана {newer}: карточка не выполнялась"

def test_stop_run_writes_only_the_run_and_keeps_its_usage(repo, capsys, monkeypatch):
    import pytest
    cid, s = seeded(repo, capsys)
    rid = run(repo, "run", "start", cid, "--step", "1", "--contracts", "3", capsys=capsys)[1].strip()
    run(repo, "run", "progress", rid, "--contracts-done", "2", capsys=capsys)
    saved = []
    monkeypatch.setattr(Store, "save_card", lambda self, card: saved.append(card.status))
    tr.stop_run(s, s.load_run(rid), note="owner stopped it", now="2026-10-21T11:00:00")()
    r = s.load_run(rid)
    assert saved == [] and r.result == "stop" and r.finished == "2026-10-21T11:00:00"
    assert r.contracts_done == 2 and r.body.endswith("owner stopped it")
    with pytest.raises(context.CliError, match="already finished"):
        tr.stop_run(s, r, note="again", now="2026-10-21T11:01:00")
