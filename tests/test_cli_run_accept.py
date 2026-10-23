from the_nod.cli import main
from the_nod.store import Store

def run(repo, *args, capsys):
    code = main(["--root", str(repo), *args]); out = capsys.readouterr(); return code, out.out, out.err

def card_with_steps(repo, capsys):
    run(repo, "init", capsys=capsys)
    cid = run(repo, "card", "add", "Экспорт", capsys=capsys)[1].strip()
    s = Store(repo / ".nod"); c = s.load_card(cid)
    from the_nod.model import Step; c.steps = [Step(1, "Таблица"), Step(2, "Статус")]; s.save_card(c)
    return cid, s

def test_run_start_finish_marks_step_and_status(repo, capsys):
    cid, s = card_with_steps(repo, capsys)
    rid = run(repo, "run", "start", cid, "--step", "1", "--contracts", "4", capsys=capsys)[1].strip()
    assert s.load_card(cid).status == "running"
    assert run(repo, "run", "start", cid, "--step", "2", capsys=capsys)[0] == 2
    run(repo, "run", "finish", rid, "--result", "ok", "--contracts-done", "4", "--tokens", "3800000", capsys=capsys)
    c = s.load_card(cid); assert c.steps[0].done and not c.steps[1].done and c.status == "ready"
    rid2 = run(repo, "run", "start", cid, "--step", "2", capsys=capsys)[1].strip()
    run(repo, "run", "finish", rid2, "--result", "ok", capsys=capsys)
    assert s.load_card(cid).status == "accepting"

def test_run_stop_returns_ready_and_double_finish_fails(repo, capsys):
    cid, s = card_with_steps(repo, capsys)
    rid = run(repo, "run", "start", cid, "--step", "1", capsys=capsys)[1].strip()
    assert run(repo, "run", "finish", rid, "--result", "stop", "--note", "завис", capsys=capsys)[0] == 0
    c = s.load_card(cid); assert c.status == "ready" and not c.steps[0].done
    assert s.load_run(rid).body == "завис"
    code, _, err = run(repo, "run", "finish", rid, "--result", "ok", capsys=capsys)
    assert code == 2 and "the run already finished" in err

def test_run_bad_step_and_bad_result(repo, capsys):
    cid, s = card_with_steps(repo, capsys)
    assert run(repo, "run", "start", cid, "--step", "9", capsys=capsys)[0] == 2
    rid = run(repo, "run", "start", cid, capsys=capsys)[1].strip()
    assert run(repo, "run", "finish", rid, "--result", "maybe", capsys=capsys)[0] == 2

def test_run_without_steps_goes_accepting(repo, capsys):
    run(repo, "init", capsys=capsys)
    cid = run(repo, "card", "add", "Без шагов", capsys=capsys)[1].strip()
    rid = run(repo, "run", "start", cid, capsys=capsys)[1].strip()
    run(repo, "run", "finish", rid, "--result", "ok", capsys=capsys)
    assert Store(repo / ".nod").load_card(cid).status == "accepting"

def test_accept_copies_small_frames_and_asks_verdict(repo, tmp_path, capsys):
    cid, s = card_with_steps(repo, capsys)
    small = tmp_path / "a.jpg"; small.write_bytes(b"x" * 1000)
    big = tmp_path / "b.jpg"; big.write_bytes(b"x" * 400_000)
    code, _, err = run(repo, "accept", cid, "--level", "2", "--result", "solved", "--evidence", "14 из 14",
                       "--frame", str(small), "--caption", "7 дней", "--frame", str(big), "--caption", "лента", capsys=capsys)
    assert code == 0 and "over 300 KB" in err
    a = s.load_acceptance(cid)
    assert a.level == 2 and a.frames[0].path == "frame-1.jpg" and a.frames[1].path == str(big)
    assert (s.root / "acceptance" / cid / "frame-1.jpg").exists()
    d = [x for x in s.decisions() if x.kind == "verdict"][0]
    assert d.card == cid and d.options == ["accept", "return"] and s.load_card(cid).status == "waiting-verdict"
    assert d.question == "Accept the verdict: Экспорт" and d.reason == "solved; 14 из 14"

def test_verdict_and_return_questions_follow_lang(repo, capsys, monkeypatch):
    cid, s = card_with_steps(repo, capsys)
    monkeypatch.setenv("NOD_LANG", "ru")
    assert run(repo, "accept", cid, "--level", "1", "--result", "solved", capsys=capsys)[0] == 0
    verdict = [x for x in s.decisions() if x.kind == "verdict"][0]
    assert verdict.question == "Принять вердикт: Экспорт"
    assert run(repo, "decision", "answer", verdict.id, "return", "--note", "нет", capsys=capsys)[0] == 0
    assert [x.question for x in s.decisions() if x.kind == "return"] == ["Вернуть на доработку: Экспорт"]
    code, _, err = run(repo, "run", "finish", "../x", "--result", "ok", capsys=capsys)
    assert code == 2 and err.startswith("ошибка: недопустимый id")

def test_accept_bad_result(repo, capsys):
    cid, _ = card_with_steps(repo, capsys)
    assert run(repo, "accept", cid, "--level", "1", "--result", "ok", capsys=capsys)[0] == 2

def test_accept_bad_level_frames_and_captions(repo, tmp_path, capsys):
    cid, _ = card_with_steps(repo, capsys)
    f = tmp_path / "a.png"; f.write_bytes(b"x")
    base = ("accept", cid, "--result", "solved")
    assert run(repo, *base, "--level", "4", capsys=capsys)[0] == 2
    assert run(repo, *base, "--level", "1", "--frame", str(f), capsys=capsys)[0] == 2
    assert run(repo, *base, "--level", "1", "--frame", str(tmp_path / "no.png"), "--caption", "x", capsys=capsys)[0] == 2
    seven = [a for _ in range(7) for a in ("--frame", str(f), "--caption", "x")]
    code, _, err = run(repo, *base, "--level", "1", *seven, capsys=capsys)
    assert code == 2 and "at most six frames" in err

def test_accept_twice_waits_for_answer(repo, capsys):
    cid, s = card_with_steps(repo, capsys)
    args = ("accept", cid, "--level", "1", "--result", "solved")
    assert run(repo, *args, capsys=capsys)[0] == 0
    code, _, err = run(repo, *args, capsys=capsys)
    assert code == 2 and "a verdict is already waiting for an answer" in err
    did = [x for x in s.decisions() if x.kind == "verdict"][0].id
    run(repo, "decision", "answer", did, "return", "--note", "нет", capsys=capsys)
    assert run(repo, *args, capsys=capsys)[0] == 0
    assert len([x for x in s.decisions() if x.kind == "verdict"]) == 2

def test_bad_ids_give_clean_error(repo, tmp_path, capsys):
    cid, _ = card_with_steps(repo, capsys)
    code, _, err = run(repo, "run", "finish", "../x", "--result", "ok", capsys=capsys)
    assert code == 2 and "invalid id" in err
    assert run(repo, "card", "show", "../x", capsys=capsys)[0] == 2
    f = tmp_path / "a.txt"; f.write_bytes(b"x")
    code, _, err = run(repo, "accept", cid, "--level", "1", "--result", "solved",
                       "--frame", str(f), "--caption", "x", capsys=capsys)
    assert code == 2 and "extension" in err


def _accept(repo, cid, capsys):
    return run(repo, "accept", cid, "--level", "1", "--result", "solved", capsys=capsys)


def test_run_start_refused_on_done_and_waiting_verdict(repo, capsys):
    cid, s = card_with_steps(repo, capsys)
    assert _accept(repo, cid, capsys)[0] == 0
    code, _, err = run(repo, "run", "start", cid, capsys=capsys)
    assert code == 2 and f"card {cid} is waiting-verdict: a run is not possible" in err
    run(repo, "card", "close", cid, capsys=capsys)
    code, _, err = run(repo, "run", "start", cid, capsys=capsys)
    assert code == 2 and f"card {cid} is done: a run is not possible" in err
    assert s.runs() == []


def test_accept_refused_on_done(repo, capsys):
    cid, s = card_with_steps(repo, capsys)
    run(repo, "card", "close", cid, capsys=capsys)
    code, _, err = _accept(repo, cid, capsys)
    assert code == 2 and f"card {cid} is already closed" in err
    assert s.load_card(cid).status == "done" and s.load_acceptance(cid) is None


def test_close_twice_refused(repo, capsys):
    cid, s = card_with_steps(repo, capsys)
    run(repo, "card", "close", cid, capsys=capsys)
    closed_at = s.load_card(cid).closed_at
    code, _, err = run(repo, "card", "close", cid, "--by", "agent", capsys=capsys)
    assert code == 2 and f"card {cid} is already closed at {closed_at}" in err
    assert s.load_card(cid).closed_by == "owner"


def test_return_from_done_allowed_twice_refused(repo, capsys):
    cid, s = card_with_steps(repo, capsys)
    run(repo, "card", "close", cid, capsys=capsys)
    assert run(repo, "card", "return", cid, "--note", "не то", capsys=capsys)[0] == 0
    code, _, err = run(repo, "card", "return", cid, "--note", "ещё раз", capsys=capsys)
    assert code == 2 and f"card {cid} is already returned" in err
    assert len(s.decisions()) == 1


def test_verdict_accept_refused_on_done_card(repo, capsys):
    cid, s = card_with_steps(repo, capsys)
    _accept(repo, cid, capsys)
    verdict = s.decisions()[0].id
    run(repo, "card", "close", cid, "--by", "agent", capsys=capsys)
    code, _, err = run(repo, "decision", "answer", verdict, "accept", capsys=capsys)
    assert code == 2 and f"card {cid} is already closed" in err
    assert s.load_decision(verdict).answer is None and s.load_card(cid).closed_by == "agent"
