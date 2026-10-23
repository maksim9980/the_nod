from the_nod.store import Store
from the_nod import model as m, snapshot

def seed(root):
    s = Store(root / ".nod")
    s.save_card(m.Card(id="c-aaaa", title="A", status="running", created="2026-10-10T00:00:00", source="owner",
                       steps=[m.Step(1, "Шаг 1", True), m.Step(2, "Шаг 2")]))
    s.save_card(m.Card(id="c-bbbb", title="B", status="backlog", created="2026-10-10T00:00:00", source="owner"))
    s.save_card(m.Card(id="c-cccc", title="C", status="done", created="2026-10-10T00:00:00", source="owner",
                       closed_at="2026-10-19T12:00:00", closed_by="owner"))
    s.save_decision(m.Decision(id="d-1111", kind="verdict", card="c-cccc", created="2026-10-19T11:00:00",
                               question="Принять вердикт: C", proposed="accept", options=["accept", "return"]))
    s.save_run(m.Run(id="r-1111", card="c-aaaa", step=2, started="2026-10-20T09:00:00", contracts_total=5, contracts_done=2))
    s.save_run(m.Run(id="r-0000", card="c-cccc", step=1, started="2026-10-18T09:00:00", finished="2026-10-18T10:00:00",
                     result="ok", tokens=3800000))
    s.set_order(["c-bbbb", "c-aaaa"])
    return s

def test_build_sections(tmp_path):
    s = seed(tmp_path)
    st = snapshot.build(s, now="2026-10-20T10:00:00", host="laptop", since="2026-10-17T00:00:00", fresh=True, stale_since=None)
    assert [d["id"] for d in st["waiting"]] == ["d-1111"] and st["waiting"][0]["card_title"] == "C"
    assert st["running"][0]["step_title"] == "Шаг 2" and st["running"][0]["contracts_done"] == 2
    assert st["since"] == {"from": "2026-10-17T00:00:00", "runs": 1, "steps_done": 1, "accepted": 0,
                           "tokens": 3800000, "cards_done": [{"id": "c-cccc", "title": "C", "closed_at": "2026-10-19T12:00:00"}]}
    assert [c["id"] for c in st["backlog"]["top"]] == ["c-bbbb", "c-aaaa"] and st["backlog"]["total"] == 2
    assert st["lock"] is None and st["fresh"] is True

def test_since_defaults_to_seen(tmp_path):
    s = seed(tmp_path); s.mark_seen("laptop", "2026-10-19T00:00:00")
    st = snapshot.build(s, now="2026-10-20T10:00:00", host="laptop", since=None, fresh=True, stale_since=None)
    assert st["since"]["from"] == "2026-10-19T00:00:00"

def test_write_is_utf8_json(tmp_path):
    s = seed(tmp_path)
    p = snapshot.write(s, {"generated_at": "x", "title": "Ёлочки «»"})
    assert p.name == "state.json" and "Ёлочки «»" in p.read_text(encoding="utf-8")


def _build(s, **kw):
    args = dict(now="2026-10-20T10:00:00", host="laptop", since="2026-10-17T00:00:00", fresh=True, stale_since=None)
    return snapshot.build(s, **{**args, **kw})

def test_open_run_of_done_card_is_not_running(tmp_path):
    s = seed(tmp_path)
    s.save_run(m.Run(id="r-2222", card="c-cccc", step=1, started="2026-10-20T09:30:00"))
    assert [r["card"] for r in _build(s)["running"]] == ["c-aaaa"]

def test_running_card_without_open_run(tmp_path):
    s = seed(tmp_path)
    s.save_run(m.Run(id="r-1111", card="c-aaaa", step=2, started="2026-10-20T09:00:00", finished="2026-10-20T09:30:00"))
    assert _build(s)["running"] == [{"card": "c-aaaa", "card_title": "A", "step": None, "step_title": None,
                                     "run": None, "started": None, "contracts_done": 0, "contracts_total": 0}]

def test_answered_decision_not_waiting(tmp_path):
    s = seed(tmp_path)
    d = s.load_decision("d-1111")
    d.answer, d.answered_at, d.answered_by = "accept", "2026-10-20T09:00:00", "owner"
    s.save_decision(d)
    assert _build(s)["waiting"] == []

def test_returned_card_not_in_backlog(tmp_path):
    s = seed(tmp_path)
    s.save_card(m.Card(id="c-dddd", title="D", status="returned", created="2026-10-10T00:00:00", source="owner"))
    s.set_order(["c-bbbb", "c-aaaa", "c-dddd"])
    assert [c["id"] for c in _build(s)["backlog"]["top"]] == ["c-bbbb", "c-aaaa"]

def test_top_limits_items_but_not_total(tmp_path):
    s = seed(tmp_path)
    s.save_card(m.Card(id="c-eeee", title="E", status="ready", created="2026-10-10T00:00:00", source="owner"))
    s.set_order(["c-bbbb", "c-aaaa", "c-eeee"])
    b = _build(s, top=2)["backlog"]
    assert len(b["top"]) == 2 and b["total"] == 3

def test_lock_is_reported(tmp_path):
    s = seed(tmp_path)
    s.write_lock("pc-1", "2026-10-20T09:00:00")
    assert _build(s)["lock"] == {"host": "pc-1", "at": "2026-10-20T09:00:00"}

def test_since_without_seen_is_week_back(tmp_path):
    s = seed(tmp_path)
    s.mark_seen("other", "2026-10-19T00:00:00")
    assert _build(s, since=None)["since"]["from"] == "2026-10-13T10:00:00"

def test_accepted_counts_only_solved_since(tmp_path):
    s = seed(tmp_path)
    s.save_acceptance(m.Acceptance(card="c-cccc", level=1, result="solved", created="2026-10-19T13:00:00"))
    s.save_acceptance(m.Acceptance(card="c-aaaa", level=1, result="unverified", created="2026-10-19T13:00:00"))
    s.save_acceptance(m.Acceptance(card="c-bbbb", level=1, result="solved", created="2026-10-01T13:00:00"))
    assert _build(s)["since"]["accepted"] == 1

def test_write_replaces_file_without_leftovers(tmp_path):
    s = seed(tmp_path)
    snapshot.write(s, {"a": 1}); snapshot.write(s, {"a": 2})
    assert '"a": 2' in (s.root / "state.json").read_text(encoding="utf-8")
    assert not list(s.root.glob("state.json.*"))

def test_schema_and_verdict_acceptance(tmp_path):
    s = seed(tmp_path)
    st = _build(s)
    assert st["schema"] == 1 and st["waiting"][0]["acceptance"] is None
    s.save_acceptance(m.Acceptance(card="c-cccc", level=2, result="solved", created="2026-10-19T13:00:00",
                                   evidence="видно", frames=[m.Frame("frame-1.png", "экран")],
                                   steps=["открыть"], report="docs/r.md"))
    assert _build(s)["waiting"][0]["acceptance"] == {
        "level": 2, "result": "solved", "evidence": "видно",
        "frames": [{"path": "frame-1.png", "caption": "экран"}], "steps": ["открыть"], "report": "docs/r.md"}

def test_review_in_snapshot_is_latest_or_none(tmp_path):
    s = seed(tmp_path)
    assert _build(s)["review"] is None
    s.save_review(m.Review(week="2026-42", since="a", until="b", generated_at="c"))
    s.save_review(m.Review(week="2026-43", since="a", until="b", generated_at="c", runs=2, suggestions=[m.Suggestion(1, "stuck", "period", "т")]))
    r = _build(s)["review"]
    assert r["week"] == "2026-43" and r["runs"] == 2 and r["suggestions"] == [{"n": 1, "text": "т", "status": "proposed"}] and r["path"] == "reviews/2026-43.md"
