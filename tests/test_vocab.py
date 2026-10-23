"""The canonical vocabulary of the state files (decision R2): values the core and the pane compare."""

import dataclasses
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from the_nod import context, model, vocab
from the_nod.cli import main
from the_nod.driver import apply_brief, plan, react
from the_nod.driver import log as dl
from the_nod.mcp import tools
from the_nod.model import Acceptance, Decision, ModelError, Suggestion
from the_nod.store import Store
from tests.driver_helpers import env_for_tests, setup

NOW = "2026-10-22T10:00:00"
CORE = Path(__file__).resolve().parent.parent / "the_nod"


def ctx_of(repo):
    return context.open(SimpleNamespace(root=str(repo)))


def add_card(repo, capsys, title="Export habits to CSV") -> str:
    main(["--root", str(repo), "card", "add", title])
    return capsys.readouterr().out.strip()


def decision(**kw) -> Decision:
    base = dict(id="d-1", kind="owner-action", created=NOW, question="Q", proposed=vocab.DONE,
                options=[vocab.DONE, vocab.POSTPONE])
    return Decision(**{**base, **kw})


# --- the table itself ---

def test_vocab_values_match_the_table():
    assert (vocab.DONE, vocab.POSTPONE) == ("done", "postpone")
    assert (vocab.YES, vocab.NO, vocab.WAIT) == ("yes", "no", "wait")
    assert (vocab.ACCEPT, vocab.RETURN) == ("accept", "return")
    assert (vocab.RERUN, vocab.BACKLOG, vocab.RESTART) == ("rerun", "backlog", "restart")
    assert (vocab.SOLVED, vocab.UNSOLVED, vocab.UNVERIFIED) == ("solved", "unsolved", "unverified")
    assert (vocab.PROPOSED, vocab.APPLIED) == ("proposed", "applied")
    assert (vocab.CONSUMED_MARK, vocab.CARD_MARK) == ("Consumed:", "Card:")


def test_vocab_values_are_ascii_identifiers():
    for name in dir(vocab):
        value = getattr(vocab, name)
        if name.isupper() and isinstance(value, str):
            assert value.isascii(), name


# --- the model ---

def test_model_accepts_only_canonical_results():
    Acceptance.from_meta({"card": "c-1", "level": 1, "result": "unverified", "created": NOW})
    with pytest.raises(ModelError):
        Acceptance.from_meta({"card": "c-1", "level": 1, "result": "решилась", "created": NOW})
    assert model.ACCEPT_RESULTS == ("solved", "unsolved", "unverified")


def test_model_accepts_only_canonical_suggestion_statuses():
    assert model.SUGGESTION_STATUSES == ("proposed", "applied")
    assert Suggestion(1, "stuck", "period", "Text").status == "proposed"
    meta = {"n": 1, "rule": "stuck", "target": "period", "text": "Text"}
    assert Suggestion.from_meta({**meta, "status": "applied"}).status == "applied"
    for old in ("предлагается", "внесено"):
        with pytest.raises(ModelError):
            Suggestion.from_meta({**meta, "status": old})


# --- decisions the driver asks ---

def test_owner_action_options_are_canonical(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    d = apply_brief.make_owner_action(s, s.load_card(cid), kind="run", text="t", now=NOW)
    assert (d.proposed, d.options) == ("done", ["done", "postpone"])


def test_next_batch_yes_no_and_pain_wait(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    main(["--root", str(repo), "card", "add", "Weekly email digest", "--source", "import"])
    capsys.readouterr()
    log = dl.Log(s.root / "driver.log")
    batch = s.load_decision(apply_brief.ask_next_batch(ctx_of(repo), log))
    assert (batch.kind, batch.proposed, batch.options) == ("next-batch", "yes", ["yes", "no"])
    pain = s.load_decision(apply_brief.ask_pain(ctx_of(repo), log))
    assert (pain.kind, pain.proposed, pain.options) == ("pain", "wait", ["wait"])


def test_verdict_return_and_stuck_options_are_canonical(repo, capsys, tmp_path, monkeypatch):
    from the_nod.commands.card import make_return_decision
    from the_nod.driver import apply_run
    from the_nod.transitions import make_acceptance
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    card = s.load_card(add_card(repo, capsys))
    verdict, _, _ = make_acceptance(s, dataclasses.replace(card), level=1, result=vocab.SOLVED, evidence="",
                                    frames=[], steps=[], report=None, now=NOW)
    assert (verdict.proposed, verdict.options) == ("accept", ["accept", "return"])
    back = make_return_decision(s, card, "note", NOW)
    assert (back.proposed, back.options) == ("rerun", ["rerun", "backlog"])
    stuck = apply_run._stuck_decision(ctx_of(repo), card, "reason")
    assert (stuck.proposed, stuck.options) == ("restart", ["restart", "backlog"])


# --- the consumed / card markers ---

def test_consumed_marker_is_english():
    d = decision()
    assert apply_brief.consumed(d, NOW).body.endswith("Consumed: " + NOW)
    assert plan.consumed(dataclasses.replace(d, body="Consumed: x")) is True
    assert plan.consumed(dataclasses.replace(d, body="Учтено: x")) is False


def test_card_marker_is_english_for_pain_only():
    pain = decision(kind="pain", proposed=vocab.WAIT, options=[vocab.WAIT])
    assert plan.consumed(dataclasses.replace(pain, body="Card: c-1")) is True
    assert plan.consumed(dataclasses.replace(pain, body="Карточка: c-1")) is False
    assert plan.consumed(dataclasses.replace(pain, body="see Card: c-1")) is False
    fork = decision(kind="fork", proposed="A", options=["A", "B"])
    assert plan.consumed(dataclasses.replace(fork, body="Card: c-1")) is False


# --- driver reactions on canonical answers ---

def answered(repo, capsys, did, answer):
    main(["--root", str(repo), "decision", "answer", did, answer])
    capsys.readouterr()


def test_postpone_on_owner_action_sends_card_to_the_bottom(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    first, second = add_card(repo, capsys, "Export habits to CSV"), add_card(repo, capsys, "Weekly email digest")
    act = apply_brief.make_owner_action(s, s.load_card(first), kind="run", text="need a key", now=NOW)
    s.save_decision(act)
    answered(repo, capsys, act.id, "postpone")
    react.react(ctx_of(repo), dl.Log(s.root / "driver.log"), plan.reactions(s.cards(), s.decisions())[0])
    assert s.load_card(first).status == "backlog" and s.order()[-1] == first and s.order()[0] == second
    assert plan.consumed(s.load_decision(act.id))


def test_done_on_owner_action_only_marks_the_decision(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    card = dataclasses.replace(s.load_card(cid), status="briefing")
    s.save_card(card)
    act = apply_brief.make_owner_action(s, card, kind="brief", text="log in", now=NOW)
    s.save_decision(act)
    answered(repo, capsys, act.id, "done")
    react.react(ctx_of(repo), dl.Log(s.root / "driver.log"), plan.reactions(s.cards(), s.decisions())[0])
    assert s.load_card(cid).status == "briefing" and s.order() == [cid]
    assert "Consumed:" in s.load_decision(act.id).body


def test_yes_on_next_batch_starts_the_batch_and_no_does_not(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    ids = [add_card(repo, capsys, t) for t in ("Export habits to CSV", "Weekly email digest")]
    for cid in ids:
        s.save_card(dataclasses.replace(s.load_card(cid), source="import"))
    log = dl.Log(s.root / "driver.log")
    did = apply_brief.ask_next_batch(ctx_of(repo), log)
    answered(repo, capsys, did, "yes")
    react.react(ctx_of(repo), log, plan.reactions(s.cards(), s.decisions())[0])
    assert [s.load_card(i).status for i in ids] == ["briefing", "briefing"]


def test_no_on_next_batch_is_not_reasked_before_reask_seconds():
    t = "2026-10-21T12:00:00"
    backlog = [model.Card(id="c-1", title="c", status="backlog", created=t, source="import")]

    def asked(answered_at):
        d = Decision(id="d-1", kind="next-batch", created=t, question="Q", proposed="yes", options=["yes", "no"],
                     answer="no", answered_at=answered_at)
        return plan.next_action(backlog, [d], [], ["c-1"], t, run_mtime=lambda rid: 0.0, clock=0.0).kind

    assert asked("2026-10-21T11:00:00") == "idle"
    assert plan.REASK_SECONDS == 86400
    assert asked("2026-10-19T11:00:00") == "next-batch"


def test_wait_on_pain_is_not_reasked_before_reask_seconds():
    t = "2026-10-21T12:00:00"

    def asked(answered_at):
        d = Decision(id="d-1", kind="pain", created=t, question="Q", proposed="wait", options=["wait"],
                     answer="wait", answered_at=answered_at)
        return plan.next_action([], [d], [], [], t, run_mtime=lambda rid: 0.0, clock=0.0).kind

    assert asked("2026-10-21T11:00:00") == "idle"
    assert asked("2026-10-19T11:00:00") == "pain"


def test_free_answer_to_pain_makes_a_card_and_writes_the_english_marker(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    log = dl.Log(s.root / "driver.log")
    pid = apply_brief.ask_pain(ctx_of(repo), log)
    main(["--root", str(repo), "decision", "answer", pid, "Search is slow\ndetails", "--free"])
    capsys.readouterr()
    react.react(ctx_of(repo), log, plan.reactions(s.cards(), s.decisions())[0])
    new = next(c for c in s.cards() if c.title == "Search is slow")
    assert f"Card: {new.id}" in s.load_decision(pid).body


def test_old_russian_answers_are_not_understood(repo, capsys, tmp_path, monkeypatch):
    """Until `nod migrate` rewrites an old state, the driver reads no Russian answer as a canonical one."""
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    card = dataclasses.replace(s.load_card(cid), status="briefing")
    s.save_card(card)
    old = decision(id="d-aaaa", card=cid, proposed="сделано", options=["сделано", "отложить"])
    s.save_decision(old)
    answered(repo, capsys, old.id, "отложить")
    log = dl.Log(s.root / "driver.log")
    react.react(ctx_of(repo), log, plan.reactions(s.cards(), s.decisions())[0])
    assert s.load_card(cid).status == "briefing"  # not sent back to the backlog
    marked = s.load_decision(old.id)
    assert plan.consumed(marked) and f"\n{vocab.CONSUMED_MARK} " in f"\n{marked.body}"
    batch = decision(id="d-2", kind="next-batch", proposed="да", options=["да", "нет"], answer="да",
                     answered_at=NOW, body=f"- {cid}  Export habits to CSV")
    assert plan.reactions([dataclasses.replace(card, status="backlog")], [batch]) == []


# --- the CLI and MCP surface ---

def test_review_mark_writes_applied(repo, capsys):
    from tests.conftest import git
    from tests.test_snapshot import seed
    s = seed(repo)
    git(repo, "add", ".nod")
    git(repo, "commit", "-m", "state: seed")
    main(["--root", str(repo), "--json", "review", "week", "--since", "2026-10-14T00:00:00"])
    week = json.loads(capsys.readouterr().out)["week"]
    assert main(["--root", str(repo), "review", "mark", week, "1", "--applied"]) == 0
    assert capsys.readouterr().out.strip().endswith("applied")
    assert s.load_review(week).suggestions[0].status == "applied"
    assert "1. [applied]" in (s.root / "reviews" / f"{week}.md").read_text(encoding="utf-8")
    assert main(["--root", str(repo), "review", "mark", week, "1", "--proposed"]) == 0
    assert s.load_review(week).suggestions[0].status == "proposed"
    assert "1. [proposed]" in (s.root / "reviews" / f"{week}.md").read_text(encoding="utf-8")


def test_accept_takes_canonical_results_only(repo, capsys):
    main(["--root", str(repo), "init"])
    capsys.readouterr()
    cid = add_card(repo, capsys)
    base = ["--root", str(repo), "accept", cid, "--level", "1"]
    assert main([*base, "--result", "решилась"]) == 2
    assert "решилась" in capsys.readouterr().err
    assert main([*base, "--result", "solved"]) == 0
    assert Store(repo / ".nod").load_acceptance(cid).result == "solved"


def test_accept_help_lists_canonical_results(capsys):
    with pytest.raises(SystemExit):
        main(["accept", "--help"])
    assert "solved | unsolved | unverified" in capsys.readouterr().out


def test_mcp_schema_uses_canonical_values():
    mark = tools.by_name["review_mark"]
    assert mark.schema["properties"]["status"]["enum"] == ["applied", "proposed"]
    assert mark.argv({"week": "2026-43", "n": 2, "status": "applied"}) == ["review", "mark", "--applied", "--", "2026-43", "2"]
    with pytest.raises(tools.MissingArgument):
        mark.argv({"week": "2026-43", "n": 2, "status": "внесено"})
    described = tools.by_name["accept"].schema["properties"]["result"]["description"]
    assert all(word in described for word in ("solved", "unsolved", "unverified"))


# --- the core carries no bare literals of these values ---

BARE = re.compile(r"""(["'])(done|postpone|yes|no|wait|solved|unsolved|unverified|proposed|applied|rerun|restart)\1""")
# Lines where a canonical word is not an answer value, exactly as they stand (file, stripped line):
# the card status `done`, JSON keys, an argument name, a rule id. Any other line with such a literal fails,
# a changed line too, until it is reviewed and listed here.
NOT_A_VALUE = {
    ("the_nod/commands/card.py", 'if card.status == "done":'),
    ("the_nod/commands/card.py", 'card.status, card.closed_at, card.closed_by = "done", ctx.now, args.by'),
    ("the_nod/commands/decision.py", 'if card.status == "done":'),
    ("the_nod/commands/decision.py", 'card.status, card.closed_at, card.closed_by = "done", ctx.now, "owner"'),
    ("the_nod/commands/install.py",  # the `nod install --json` key
     'context.emit(args, {"done": done, "ok": ok, "checks": [asdict(check) for check in after]},'),
    ("the_nod/commands/status.py",  # the snapshot key read by `nod status`
     """waiting = [f"{d['id']}  {d['question']}  → {d['proposed']}" for d in state["waiting"]]"""),
    ("the_nod/i18n/en/doctor.py", '"doctor.no": "no",'),  # the words of the doctor table, not state values
    ("the_nod/i18n/en/doctor.py", '"doctor.yes": "yes",'),
    ("the_nod/i18n/en/doctor.py", '"install.done": "done",'),
    ("the_nod/mcp/tools.py", '_opt("proposed", "string", d("mcp.arg_proposed"), required=True),'),  # an argument name
    ("the_nod/migrate.py", 'VALUE_FIELDS = ("answer", "proposed")'),  # decision field names
    ("the_nod/model.py", '"accepting", "waiting-verdict", "done", "returned",'),  # CARD_STATUSES
    ("the_nod/render.py", 'done = sorted((c for c in store.cards() if c.status == "done"), key=lambda c: c.id)'),
    ("the_nod/review/rules.py", '("unverified", _unverified),'),  # a review rule id
    ("the_nod/snapshot.py", '_CLOSED = ("done", "returned")'),  # closed card statuses
    ("the_nod/snapshot.py", '"question": d.question, "proposed": d.proposed, "options": list(d.options),'),
    ("the_nod/snapshot.py",
     'done = sorted((c for c in cards if c.status == "done" and c.closed_at and c.closed_at >= since),'),
    ("the_nod/transitions.py", 'NO_RUN_STATUSES = ("done", "waiting-verdict")'),
    ("the_nod/transitions.py", 'if card.status == "done":'),
}


def bare_literals() -> set[tuple[str, str]]:
    """(file, stripped line) of every core line with a bare canonical value literal."""
    found = set()
    for path in sorted(CORE.rglob("*.py")):
        if path.name == "vocab.py":
            continue
        rel = path.relative_to(CORE.parent).as_posix()
        for line in path.read_text(encoding="utf-8").splitlines():
            if BARE.search(line):
                found.add((rel, line.strip()))
    return found


def test_core_modules_use_the_constants():
    assert sorted(bare_literals() - NOT_A_VALUE) == []


def test_every_exempt_line_still_exists():
    """A stale exemption would let a new literal in on the same text: the list stays exact."""
    assert sorted(NOT_A_VALUE - bare_literals()) == []


def test_scan_catches_a_substring_that_used_to_pass():
    """The old guard skipped any line with `status` in it; a value next to a status is now caught."""
    line = 'if card.status == "backlog" and d.answer == "rerun":'
    assert BARE.search(line) and ("the_nod/x.py", line) not in NOT_A_VALUE
