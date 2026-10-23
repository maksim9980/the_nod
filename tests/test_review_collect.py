# tests/test_review_collect.py
import pytest

from the_nod import i18n
from the_nod import model as m
from the_nod.review.collect import CardStat, collect
from the_nod.store import Store
from tests.driver_helpers import add_card, driver_run, env_for_tests, setup

SINCE, UNTIL = "2026-10-14T00:00:00", "2026-10-21T00:00:00"
SUBJECTS = ["state: driver brief c-bbbb briefing"] * 3 + ["state: run start r-0000"]


def seed_review(root):
    s = Store(root / ".nod")
    for id, title, status in (("c-aaaa", "A", "running"), ("c-bbbb", "B", "backlog"), ("c-cccc", "C", "done")):
        s.save_card(m.Card(id=id, title=title, status=status, created="2026-10-10T00:00:00", source="owner"))
    s.save_run(m.Run(id="r-0000", card="c-cccc", step=1, started="2026-10-18T09:00:00", finished="2026-10-18T10:00:00",
                     result="ok", tokens=3800000, minutes=60))
    s.save_run(m.Run(id="r-2222", card="c-aaaa", step=1, started="2026-10-19T09:00:00", finished="2026-10-19T09:30:00",
                     result="stop", tokens=0, body="the agent said stop"))
    s.save_decision(m.Decision(id="d-1111", kind="verdict", card="c-cccc", created="2026-10-19T11:00:00",
                               question="Accept the verdict: C", proposed="accept", options=["accept", "return"]))
    s.save_decision(m.Decision(id="d-2222", kind="run-stuck", card="c-aaaa", created="2026-10-20T10:00:00",
                               question="Stuck", proposed="restart", options=["restart", "backlog"]))
    s.save_spend(m.Spend(kind="brief", card="c-bbbb", at="2026-10-20T12:00:00", tokens=2000, minutes=3))
    s.save_spend(m.Spend(kind="accept", card="c-cccc", at="2026-10-18T11:00:00", tokens=500, minutes=1))
    s.save_acceptance(m.Acceptance(card="c-cccc", level=1, result="unverified", created="2026-10-18T11:00:00",
                                   evidence="no test environment"))
    return s


def test_collect_counts_period(tmp_path):
    st = collect(seed_review(tmp_path), since=SINCE, until=UNTIL, subjects=SUBJECTS)
    assert (st.runs, st.steps_done, st.stops, st.stuck) == (2, 1, 1, 1)
    assert st.repeats == [] and st.commits == 4 and st.brief_attempts == {"c-bbbb": 3}
    assert st.tokens == 3800000 + 2000 + 500 and st.minutes == 60 + 0 + 3 + 1
    assert st.accepted == 0 and st.unverified == 1
    assert [k.kind for k in st.kinds] == ["brief", "run", "accept"]
    assert (st.kinds[1].calls, st.kinds[1].median, st.kinds[1].maximum) == (2, 3800000, 3800000)
    assert [(d.id, d.hours) for d in st.open_over_day] == [("d-1111", 37)]
    assert (st.asked, st.answered, st.median_answer_hours) == (2, 0, None)
    assert st.cards[0] == CardStat("c-cccc", "C", 0, 1, 0, 1, 3800500, 61, "done")
    assert [(c.id, c.briefs, c.stops) for c in st.cards] == [("c-cccc", 0, 0), ("c-bbbb", 3, 0), ("c-aaaa", 0, 1)]
    assert st.failed_briefs == []
    assert [(r.id, r.note) for r in st.run_rows] == [("r-0000", ""), ("r-2222", "the agent said stop")]
    assert [(r.kind, r.title) for r in st.spend_rows] == [("accept", "C"), ("brief", "B")]
    assert [(c.label, c.tokens, c.outcome) for c in st.costly] == [
        ("r-0000 step 1", 3800000, "ok"), ("brief c-bbbb", 2000, "—"), ("accept c-cccc", 500, "—"),
        ("r-2222 step 1", 0, "stop")]


def test_collect_brief_attempts_from_usage_without_git(tmp_path):
    st = collect(seed_review(tmp_path), since=SINCE, until=UNTIL, subjects=[])
    assert st.commits == 0 and st.brief_attempts == {"c-bbbb": 1}


def test_collect_answers_repeats_and_failed_briefs(tmp_path):
    s = seed_review(tmp_path)
    s.save_run(m.Run(id="r-3333", card="c-aaaa", step=1, started="2026-10-20T09:00:00"))
    s.save_run(m.Run(id="r-4444", card="c-aaaa", step=1, started="2026-10-01T09:00:00", finished="2026-10-01T10:00:00"))
    s.save_decision(m.Decision(id="d-3333", kind="return", card="c-bbbb", created="2026-10-15T10:00:00",
                               question="Return it", proposed="return", options=["return"], answer="return",
                               answered_at="2026-10-15T13:00:00", note="brief failed: no answer"))
    st = collect(s, since=SINCE, until=UNTIL, subjects=[])
    assert st.runs == 3 and st.repeats == ["c-aaaa step 1 — 2 times"]
    assert (st.asked, st.answered, st.median_answer_hours) == (3, 1, 3)
    assert st.failed_briefs == ["c-bbbb"]
    assert [c.label for c in st.costly if c.outcome == "running"] == ["r-3333 step 1"]


def test_collect_empty_store(tmp_path):
    st = collect(Store(tmp_path / ".nod"), since=SINCE, until=UNTIL, subjects=[])
    assert st.runs == 0 and st.kinds[1].median == 0 and st.median_answer_hours is None
    assert st.cards == [] and st.open_over_day == [] and len(st.kinds) == 3


def test_collect_unknown_card_title_is_dash(tmp_path):
    s = Store(tmp_path / ".nod")
    s.save_run(m.Run(id="r-9999", card="c-zzzz", started="2026-10-20T09:00:00", finished="2026-10-20T10:00:00",
                     result="ok", tokens=7))
    st = collect(s, since=SINCE, until=UNTIL, subjects=[])
    assert st.cards == [CardStat("c-zzzz", "—", 0, 1, 0, 0, 7, 0, "—")]


def test_run_median_counts_paid_runs_only(tmp_path):
    s = Store(tmp_path / ".nod")
    s.save_card(m.Card(id="c-aaaa", title="A", status="running", created="2026-10-10T00:00:00", source="owner"))
    for id, tokens, finished in (("r-1111", 10_000_000, "2026-10-15T10:00:00"), ("r-2222", 4_000_000, "2026-10-16T10:00:00"),
                                 ("r-3333", 0, None)):
        s.save_run(m.Run(id=id, card="c-aaaa", step=1, started="2026-10-15T09:00:00", finished=finished,
                         result="ok" if finished else None, tokens=tokens))
    st = collect(s, since=SINCE, until=UNTIL, subjects=[])
    assert (st.kinds[1].calls, st.kinds[1].tokens, st.kinds[1].median, st.kinds[1].maximum) == (
        3, 14_000_000, 7_000_000, 10_000_000)


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_failed_brief_from_the_driver_is_counted(repo, capsys, tmp_path, monkeypatch, lang):
    """The driver writes the failed-brief note in the project language; the review finds it in any language."""
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys, brief="brief-fail", lang=lang)
    cid = add_card(repo, capsys)
    for _ in range(2):
        driver_run(repo, "once", capsys=capsys)
    note = [d for d in s.decisions() if d.kind == "return"][0].reason
    assert note.startswith({"en": "brief failed: ", "ru": "бриф не получился: "}[lang])
    i18n.use("ru" if lang == "en" else "en")  # the reader may use another language than the driver did
    st = collect(s, since="2000-01-01T00:00:00", until="2100-01-01T00:00:00", subjects=[])
    assert st.failed_briefs == [cid]


def test_other_return_notes_are_not_failed_briefs(tmp_path):
    s = seed_review(tmp_path)
    s.save_decision(m.Decision(id="d-3333", kind="return", card="c-bbbb", created="2026-10-15T10:00:00",
                               question="Return", proposed="rerun", options=["rerun", "backlog"],
                               note="the run command is not built: brief failed: no"))
    assert collect(s, since=SINCE, until=UNTIL, subjects=[]).failed_briefs == []


def test_collect_texts_in_russian(tmp_path):
    i18n.use("ru")
    s = seed_review(tmp_path)
    s.save_run(m.Run(id="r-3333", card="c-aaaa", step=1, started="2026-10-20T09:00:00"))
    st = collect(s, since=SINCE, until=UNTIL, subjects=[])
    assert st.repeats == ["c-aaaa шаг 1 — 2 раза"]
    assert [c.label for c in st.costly if c.outcome == "идёт"] == ["r-3333 шаг 1"]
    assert "r-0000 шаг 1" in [c.label for c in st.costly]


def test_repeats_take_the_plural_form_of_the_language(tmp_path):
    s = Store(tmp_path / ".nod")
    for i in range(5):
        s.save_run(m.Run(id=f"r-{i}{i}{i}{i}", card="c-aaaa", step=1, started="2026-10-20T09:00:00"))
    assert collect(s, since=SINCE, until=UNTIL, subjects=[]).repeats == ["c-aaaa step 1 — 5 times"]
    i18n.use("ru")
    assert collect(s, since=SINCE, until=UNTIL, subjects=[]).repeats == ["c-aaaa шаг 1 — 5 раз"]


def test_collect_rejects_unreadable_bounds(tmp_path):
    with pytest.raises(ValueError, match="period: unreadable bounds"):
        collect(Store(tmp_path / ".nod"), since="yesterday", until=UNTIL, subjects=[])
    i18n.use("ru")
    with pytest.raises(ValueError, match="период: нечитаемые границы"):
        collect(Store(tmp_path / ".nod"), since="yesterday", until=UNTIL, subjects=[])


@pytest.mark.parametrize("note", ["brief failed: no answer", "бриф не получился: нет ответа"])
def test_failed_brief_note_of_either_language_is_counted(tmp_path, note):
    s = seed_review(tmp_path)
    s.save_decision(m.Decision(id="d-3333", kind="return", card="c-bbbb", created="2026-10-15T10:00:00",
                               question="Return it", proposed="rerun", options=["rerun", "backlog"], note=note))
    assert collect(s, since=SINCE, until=UNTIL, subjects=[]).failed_briefs == ["c-bbbb"]


@pytest.mark.parametrize("reason", ["brief failed: no answer", "бриф не получился: нет ответа"])
def test_failed_brief_reason_of_either_language_is_counted(tmp_path, reason):
    """The driver writes its text into `reason`; a `note` from an older state is still read above."""
    s = seed_review(tmp_path)
    s.save_decision(m.Decision(id="d-3333", kind="return", card="c-bbbb", created="2026-10-15T10:00:00",
                               question="Return it", proposed="rerun", options=["rerun", "backlog"], reason=reason))
    assert collect(s, since=SINCE, until=UNTIL, subjects=[]).failed_briefs == ["c-bbbb"]
