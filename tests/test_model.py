import pytest
from the_nod import model as m

def test_card_roundtrip():
    c = m.Card(id="c-7k3q", title="Двигать срок", status="backlog", created="2026-10-20T10:00:00",
               source="owner", steps=[m.Step(1, "Поле даты"), m.Step(2, "Вебхук", True)], body="Текст")
    meta = c.to_meta()
    assert "body" not in meta and "brief" not in meta
    assert meta["steps"] == [{"n": 1, "title": "Поле даты", "done": False}, {"n": 2, "title": "Вебхук", "done": True}]
    assert m.Card.from_meta(meta, "Текст") == c

def test_bad_status_raises():
    with pytest.raises(m.ModelError, match="status"):
        m.Card.from_meta({"id": "c-1", "title": "t", "status": "idle", "created": "x", "source": "owner"})

def test_decision_unanswered_by_default():
    d = m.Decision(id="d-1", kind="fork", created="x", question="Q?", proposed="A", options=["A", "B"])
    assert d.answer is None and m.Decision.from_meta(d.to_meta()) == d

def test_acceptance_result_checked():
    with pytest.raises(m.ModelError, match="result"):
        m.Acceptance.from_meta({"card": "c-1", "level": 2, "result": "ok", "created": "x"})

def test_now_iso_format():
    assert len(m.now_iso()) == 19 and m.now_iso()[10] == "T"

def test_run_roundtrip_skips_none():
    r = m.Run(id="r-1", card="c-1", started="2026-10-20T10:00:00", step=2, tokens=500, body="лог")
    meta = r.to_meta()
    assert "finished" not in meta and "result" not in meta and meta["step"] == 2
    assert m.Run.from_meta(meta, "лог") == r

def test_acceptance_roundtrip_with_frames():
    a = m.Acceptance(card="c-1", level=3, result="solved", created="2026-10-20T12:00:00",
                     frames=[m.Frame("a.png", "Экран")], steps=["открыть", "нажать"], body="итог")
    meta = a.to_meta()
    assert meta["frames"] == [{"path": "a.png", "caption": "Экран"}]
    assert m.Acceptance.from_meta(meta, "итог") == a

def test_decision_answered_roundtrip():
    d = m.Decision(id="d-2", kind="verdict", created="x", question="Q?", proposed="A", options=["A"],
                   card="c-1", answer="A", answered_at="y", answered_by="owner", note="ок")
    assert m.Decision.from_meta(d.to_meta()) == d

@pytest.mark.parametrize("cls, meta, field", [
    (m.Card, {"id": "c", "title": "t", "status": "backlog", "created": "x", "source": "bot"}, "source"),
    (m.Decision, {"id": "d", "kind": "nope", "created": "x", "question": "q", "proposed": "a", "options": []}, "kind"),
    (m.Acceptance, {"card": "c", "level": 4, "result": "solved", "created": "x"}, "level"),
])
def test_invalid_values_name_the_field(cls, meta, field):
    with pytest.raises(m.ModelError, match=field):
        cls.from_meta(meta)

def test_missing_required_field_and_unknown_keys():
    with pytest.raises(m.ModelError, match="title"):
        m.Step.from_meta({"n": 1})
    assert m.Step.from_meta({"n": 1, "title": "t", "лишнее": 5}) == m.Step(1, "t")

def test_defaults_are_not_shared():
    a = m.Card(id="a", title="t", status="backlog", created="x", source="owner")
    b = m.Card(id="b", title="t", status="backlog", created="x", source="owner")
    a.steps.append(m.Step(1, "s"))
    assert b.steps == []

@pytest.mark.parametrize("steps", ["строка", 5, [1, 2], [{"n": 1, "title": "t"}, "x"]])
def test_nested_not_list_of_tables_raises_model_error(steps):
    meta = {"id": "c-1", "title": "t", "status": "backlog", "created": "x", "source": "owner", "steps": steps}
    with pytest.raises(m.ModelError, match="steps"):
        m.Card.from_meta(meta)
