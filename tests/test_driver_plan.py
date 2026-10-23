from the_nod import model as m
from the_nod.driver import plan

T = "2026-10-21T12:00:00"
def card(id, status, source="owner", steps=(), brief=None):
    return m.Card(id=id, title=id, status=status, created=T, source=source, brief=brief, steps=[m.Step(n, t, d) for n, t, d in steps])
def dec(id, kind, card=None, answer=None, proposed="yes", options=("yes", "no"), body="", answered_at=None):
    return m.Decision(id=id, kind=kind, created=T, question="Q", proposed=proposed, options=list(options), card=card, answer=answer, answered_at=answered_at, body=body)
def nxt(cards, decisions=(), runs=(), order=None, clock=0.0, mtime=lambda rid: 0.0):
    return plan.next_action(cards, list(decisions), list(runs), order or [c.id for c in cards], T, run_mtime=mtime, clock=clock)

def test_owner_card_briefed_import_card_waits_for_batch():
    assert nxt([card("c-1", "backlog", "import")]).kind == "next-batch"
    assert nxt([card("c-1", "backlog", "import"), card("c-2", "backlog")]) == plan.Action("brief", card="c-2")

def test_batch_not_reasked_while_open_or_recently_declined():
    cards = [card("c-1", "backlog", "import")]
    assert nxt(cards, [dec("d-1", "next-batch")]).kind == "idle"
    assert nxt(cards, [dec("d-1", "next-batch", answer="no", answered_at="2026-10-21T11:00:00")]).kind == "idle"
    assert nxt(cards, [dec("d-1", "next-batch", answer="no", answered_at="2026-10-19T11:00:00")]).kind == "next-batch"

def test_pain_when_everything_empty():
    assert nxt([card("c-9", "done")]).kind == "pain"
    assert nxt([], [dec("d-1", "pain", answer="wait", proposed="wait", options=("wait",), answered_at="2026-10-21T11:00:00")]).kind == "idle"

def test_run_first_ready_without_open_decisions_one_at_a_time():
    ready = card("c-1", "ready", steps=[(1, "a", True), (2, "b", False)]); other = card("c-2", "ready", steps=[(1, "a", False)])
    assert nxt([ready, other]) == plan.Action("run", card="c-1", step=2)
    assert nxt([ready, other], [dec("d-1", "fork", card="c-1")]) == plan.Action("run", card="c-2", step=1)
    assert nxt([ready, card("c-3", "running")], runs=[m.Run(id="r-1", card="c-3", started=T)], clock=10.0).kind == "idle"

def test_stuck_and_accept_come_first():
    from datetime import datetime
    running = card("c-3", "running"); run = m.Run(id="r-1", card="c-3", started=T)
    started = datetime.fromisoformat(T).timestamp()
    late = started + plan.STUCK_SECONDS + 1
    assert nxt([card("c-1", "accepting"), running], runs=[run], clock=late).kind == "stuck"
    assert nxt([card("c-1", "accepting"), running], runs=[run], clock=late, mtime=lambda r: started + plan.STUCK_SECONDS - 60).kind == "accept"

def test_consumed_decisions_give_no_reactions():
    done = dec("d-9", "fork", card="c-1", answer="B", proposed="A", options=("A", "B"), body="Consumed: 2026-10-21T12:00:00")
    assert plan.reactions([card("c-1", "waiting-owner")], [done]) == []
    assert plan.all_proposed([done, dec("d-8", "fork", card="c-1", answer="A", proposed="A", options=("A", "B"))]) is True

def test_reactions_only_for_unapplied():
    forks = [dec("d-1", "fork", card="c-1", answer="A", proposed="A", options=("A", "B")), dec("d-2", "fork", card="c-1", answer="B", proposed="A", options=("A", "B"))]
    assert plan.reactions([card("c-1", "waiting-owner")], forks)[0] == plan.Action("react", card="c-1", decision="d-1")
    assert plan.reactions([card("c-1", "briefing")], forks) == []
    assert plan.all_proposed(forks) is False and plan.all_proposed(forks[:1]) is True
    ret = dec("d-3", "return", card="c-2", answer="rerun", proposed="rerun", options=("rerun", "backlog"))
    assert plan.reactions([card("c-2", "returned")], [ret]) == [plan.Action("react", card="c-2", decision="d-3")]
    assert plan.reactions([card("c-2", "briefing")], [ret]) == []
    batch = dec("d-4", "next-batch", answer="yes", body="- c-5  Five\n- c-6  Six\n")
    assert plan.reactions([card("c-5", "backlog", "import"), card("c-6", "briefing", "import")], [batch]) == [plan.Action("react", decision="d-4")]
    assert plan.reactions([card("c-5", "briefing", "import")], [batch]) == []
    pain = dec("d-5", "pain", answer="search is slow", proposed="wait", options=("wait",))
    assert plan.reactions([], [pain]) == [plan.Action("react", decision="d-5")]
    assert plan.reactions([], [dec("d-5", "pain", answer="search is slow", proposed="wait", options=("wait",), body="Card: c-7")]) == []
    act = dec("d-6", "owner-action", card="c-8", answer="done", proposed="done", options=("done", "postpone"))
    assert plan.reactions([card("c-8", "briefing")], [act]) == [plan.Action("react", card="c-8", decision="d-6")]
    assert plan.reactions([card("c-8", "briefing")], [dec("d-6", "owner-action", card="c-8", answer="done", proposed="done", options=("done", "postpone"), body="Consumed: 2026-10-21T12:00:00")]) == []

def test_open_owner_action_blocks_card_but_not_others():
    waiting = card("c-8", "briefing"); other = card("c-9", "backlog")
    assert nxt([waiting, other], [dec("d-6", "owner-action", card="c-8", proposed="done", options=("done", "postpone"))]) == plan.Action("brief", card="c-9")

def test_accepting_with_open_decision_is_not_accepted():
    acc = card("c-1", "accepting")
    assert nxt([acc], [dec("d-1", "owner-action", card="c-1", proposed="done", options=("done",))]).kind == "idle"

def test_running_without_open_run_is_stuck():
    assert nxt([card("c-3", "running")]) == plan.Action("stuck", card="c-3", run=None)

def test_open_run_of_running_card_blocks_new_run():
    ready = card("c-1", "ready", steps=[(1, "a", False)]); busy = card("c-2", "running")
    assert nxt([ready, busy], runs=[m.Run(id="r-1", card="c-2", started=T)], clock=10.0).kind == "idle"

def test_open_run_of_card_not_running_does_not_block_new_run():
    # an old state: `nod card return` used to leave the run of the returned card open
    ready = card("c-9", "ready", steps=[(1, "a", False)]); run = m.Run(id="r-1", card="c-1", started=T)
    for status in ("returned", "ready", "backlog", "waiting-owner", "done"):
        assert nxt([card("c-1", status), ready], runs=[run], order=["c-9", "c-1"]) == plan.Action("run", card="c-9", step=1), status
    assert nxt([ready], runs=[run]) == plan.Action("run", card="c-9", step=1)  # the card of the run is gone

def test_open_run_of_returned_card_is_not_stuck_and_finished_run_is_ignored():
    run = m.Run(id="r-1", card="c-1", started=T)
    assert nxt([card("c-1", "returned")], runs=[run], clock=10 ** 12).kind == "idle"
    ready = card("c-9", "ready", steps=[(1, "a", False)]); done = m.Run(id="r-2", card="c-9", started=T, finished=T)
    assert nxt([ready], runs=[done]) == plan.Action("run", card="c-9", step=1)

def test_order_differs_and_lacks_ids():
    cards = [card("c-1", "backlog"), card("c-2", "backlog"), card("c-3", "backlog")]
    assert nxt(cards, order=["c-3"]) == plan.Action("brief", card="c-3")
    assert [c.id for c in plan.batch_cards(cards, ["c-3"])] == ["c-3", "c-1", "c-2"]

def test_batch_cards_skips_open_decisions():
    cards = [card("c-1", "backlog", "import"), card("c-2", "backlog", "import")]
    assert [c.id for c in plan.batch_cards(cards, [], [dec("d-1", "owner-action", card="c-1")])] == ["c-2"]

def test_blocked_owner_backlog_card_still_gives_next_batch():
    cards = [card("c-1", "backlog")]
    assert nxt(cards, [dec("d-1", "owner-action", card="c-1")]).kind == "next-batch"

def test_declined_batch_without_answered_at_does_not_block():
    cards = [card("c-1", "backlog", "import")]
    assert nxt(cards, [dec("d-1", "next-batch", answer="no")]).kind == "next-batch"

def test_consumed_marker_mid_line_does_not_count():
    d = dec("d-9", "fork", card="c-1", answer="B", proposed="A", options=("A", "B"), body="see Consumed: later")
    assert plan.reactions([card("c-1", "waiting-owner")], [d]) == [plan.Action("react", card="c-1", decision="d-9")]

def test_consumed_public_marks_and_pain_card_line():
    assert plan.consumed(dec("d-1", "fork", body="Consumed: 2026-10-21T12:00:00")) is True
    assert plan.consumed(dec("d-2", "fork", body="Card: c-1")) is False
    assert plan.consumed(dec("d-3", "pain", body="Card: c-1")) is True
    assert plan.consumed(dec("d-4", "pain", body="see Card: c-1")) is False

def test_ready_card_that_owns_an_open_run_is_run_when_first_in_order():
    # `start_run` closes the abandoned run of the card: the planner neither waits for it nor skips the card
    owner = card("c-1", "ready", steps=[(1, "a", False)]); other = card("c-2", "ready", steps=[(1, "a", False)])
    run = m.Run(id="r-1", card="c-1", started=T)
    cards = [card("c-3", "backlog"), other, owner]
    assert nxt(cards, runs=[run], order=["c-1", "c-3", "c-2"]) == plan.Action("run", card="c-1", step=1)
    assert nxt(cards, runs=[run], order=["c-2", "c-3", "c-1"]) == plan.Action("run", card="c-2", step=1)
