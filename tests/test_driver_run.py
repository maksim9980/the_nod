"""The run and acceptance executor: a step run, its result, the hang, the acceptance and the guard."""
import json
from pathlib import Path
from types import SimpleNamespace
from the_nod import context, harness
import pytest

from the_nod.driver import apply_run, files, lock, log as dl, plan, react
from the_nod.store import Store
from the_nod.cli import main
from tests.driver_helpers import env_for_tests, fake, setup
from tests.fake_agent import STEPS, TITLE

def ctx_of(repo): return context.open(SimpleNamespace(root=str(repo)))
def ready_card(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    from the_nod.driver import apply_brief
    h = harness.Harness("default", "", {**harness.load(s).commands, "brief": fake("brief-ok")})
    apply_brief.brief(ctx_of(repo), h, dl.Log(s.root / "driver.log"), cid)
    return cid, s
def h_with(s, **modes):
    base = harness.load(s).commands
    return harness.Harness("default", "", {**base, **{k: fake(v) for k, v in modes.items()}})

def test_run_ok_marks_step_and_usage(repo, capsys, monkeypatch, tmp_path):
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    assert apply_run.run_step(ctx_of(repo), h_with(s, run="run-ok"), dl.Log(s.root / "driver.log"), cid, 1) is True
    c = s.load_card(cid); r = s.runs()[0]
    assert c.status == "ready" and c.steps[0].done and r.result == "ok" and r.contracts_done == 3
    fixture = json.loads((Path(__file__).parent / "fixtures" / "claude" / "result.json").read_text(encoding="utf-8"))
    # The spend counts `modelUsage` (subagents included), as `usage.measure` and tests/test_driver_usage.py do.
    assert r.tokens == sum(int(m[k]) for m in fixture["modelUsage"].values() for k in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens"))
    prompt = (s.root / "driver" / f"{cid}.run.prompt.md").read_text(encoding="utf-8")
    assert STEPS[0] in prompt and r.id in prompt

def test_run_progress_from_agent_reaches_run_file(repo, capsys, monkeypatch, tmp_path):
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    apply_run.run_step(ctx_of(repo), h_with(s, run="run-progress"), dl.Log(s.root / "driver.log"), cid, 1)
    assert "contracts done: 1" in s.runs()[0].body

def test_run_stop_returns_card_with_decision(repo, capsys, monkeypatch, tmp_path):
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    assert apply_run.run_step(ctx_of(repo), h_with(s, run="run-stop"), dl.Log(s.root / "driver.log"), cid, 1) is False
    d = [x for x in s.decisions() if x.kind == "return"][0]
    assert s.load_card(cid).status == "returned" and s.runs()[0].result == "stop"
    assert (d.reason, d.note) == ("stop: test", "")  # the note is only ever the owner's

def test_run_blocked_waits_owner_then_repeats(repo, capsys, monkeypatch, tmp_path):
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    assert apply_run.run_step(ctx_of(repo), h_with(s, run="run-blocked"), dl.Log(s.root / "driver.log"), cid, 1) is False
    d = [x for x in s.decisions() if x.kind == "owner-action"][0]
    assert d.question == "the test environment on :8001 is down" and s.load_card(cid).status == "ready" and s.runs()[0].result == "stop"
    assert not [x for x in s.decisions() if x.kind == "return"]
    assert plan.next_action(s.cards(), s.decisions(), s.runs(), s.order(), "2026-10-21T12:00:00", run_mtime=lambda r: 0.0, clock=0.0).kind == "idle"

def test_stuck_run_killed_and_asks_owner(repo, capsys, monkeypatch, tmp_path):
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    monkeypatch.setattr(plan, "STUCK_SECONDS", 1.0)
    assert apply_run.run_step(ctx_of(repo), h_with(s, run="run-hang"), dl.Log(s.root / "driver.log"), cid, 1) is False
    d = [x for x in s.decisions() if x.kind == "run-stuck"][0]
    assert d.options == ["restart", "backlog"] and d.proposed == "restart" and d.card == cid and s.load_card(cid).status == "returned"
    assert "hung" in s.runs()[0].body

def test_heartbeat_refreshes_lock_during_run(repo, capsys, monkeypatch, tmp_path):
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    import subprocess
    monkeypatch.setattr(lock, "HEARTBEAT_SECONDS", 0.5)
    apply_run.run_step(ctx_of(repo), h_with(s, run="run-slow"), dl.Log(s.root / "driver.log"), cid, 1)
    assert "state: driver heartbeat" in subprocess.run(["git", "log", "--format=%s"], cwd=repo, capture_output=True, text=True, encoding="utf-8").stdout

def test_card_deleted_during_run_is_restored_with_owner_action(repo, capsys, monkeypatch, tmp_path):
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    assert apply_run.run_step(ctx_of(repo), h_with(s, run="run-delete-card"), dl.Log(s.root / "driver.log"), cid, 1) is False
    # an uncommitted removal of the card is a state edit that bypasses nod: the card is restored
    d = [x for x in s.decisions() if x.kind == "owner-action"][0]
    assert d.question == "the agent changed the .nod state — restored, check"
    assert s.load_card(cid).status == "ready" and (s.root / "driver" / f"{cid}.run.toml").exists()

def test_finish_when_stale_keeps_result(repo, capsys, monkeypatch, tmp_path):
    from the_nod.gitsync import GitSync
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    ctx = ctx_of(repo)
    monkeypatch.setattr(GitSync, "pull_ff", lambda self: False)
    assert apply_run.run_step(ctx, h_with(s, run="run-ok"), dl.Log(s.root / "driver.log"), cid, 1) is False
    assert s.load_card(cid).status == "running" and "the state is stale" in (s.root / "driver.log").read_text(encoding="utf-8")

def test_accept_ok_and_fail(repo, capsys, monkeypatch, tmp_path):
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    for step in (1, 2):
        apply_run.run_step(ctx_of(repo), h_with(s, run="run-ok"), dl.Log(s.root / "driver.log"), cid, step)
    assert s.load_card(cid).status == "accepting"
    assert apply_run.accept(ctx_of(repo), h_with(s, accept="accept-ok"), dl.Log(s.root / "driver.log"), cid) is True
    a = s.load_acceptance(cid); d = [x for x in s.decisions() if x.kind == "verdict"][0]
    assert a.level == 2 and a.frames[0].path == "frame-1.png" and a.frames[0].caption == "7 days" and a.steps == ["Open the site"]
    assert s.load_card(cid).status == "waiting-verdict" and d.card == cid
    main(["--root", str(repo), "decision", "answer", d.id, "return", "--note", "not that"])
    c = s.load_card(cid); c.status = "accepting"; s.save_card(c)
    from tests.conftest import git
    git(repo, "commit", "-am", "state: accepting")  # `lock.claim` leaves a dirty tree alone
    assert apply_run.accept(ctx_of(repo), h_with(s, accept="accept-fail"), dl.Log(s.root / "driver.log"), cid) is False
    a2 = s.load_acceptance(cid)
    assert a2.result == "unverified" and a2.evidence.startswith("acceptance failed:")


# --- behaviour from the controller rulings that the brief did not cover ---

def test_hooks_changed_during_run_stops_and_asks_owner(repo, capsys, monkeypatch, tmp_path):
    from itertools import count
    from the_nod.driver import agent
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    calls = count()
    monkeypatch.setattr(agent, "hooks_snapshot", lambda folder: {"pre-commit": str(next(calls))})
    assert apply_run.run_step(ctx_of(repo), h_with(s, run="run-ok"), dl.Log(s.root / "driver.log"), cid, 1) is False
    d = [x for x in s.decisions() if x.kind == "owner-action"][0]
    r = s.runs()[0]
    assert "pre-commit" in d.question and r.result == "stop" and "the agent changed .git/hooks" in r.body
    card = s.load_card(cid)
    assert card.status == "ready" and not card.steps[0].done
    assert not [x for x in s.decisions() if x.kind == "return"]

def test_stuck_without_run_returns_card(repo, capsys, monkeypatch, tmp_path):
    from tests.conftest import git
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    c = s.load_card(cid); c.status = "running"; s.save_card(c)
    git(repo, "commit", "-am", "state: running")
    assert apply_run.stuck(ctx_of(repo), dl.Log(s.root / "driver.log"), cid, None) is True
    d = [x for x in s.decisions() if x.kind == "run-stuck"][0]
    assert d.reason == "the card is running without a run" and d.card == cid and d.options == ["restart", "backlog"]
    assert s.load_card(cid).status == "returned" and not s.runs()

def test_hooks_changed_when_agent_closed_run_still_asks_owner(repo, capsys, monkeypatch, tmp_path):
    from itertools import count
    from the_nod.driver import agent, files
    from the_nod.transitions import RunUsage, finish_run
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    calls = count()
    monkeypatch.setattr(agent, "hooks_snapshot", lambda folder: {"pre-commit": str(next(calls))})
    real = files.reopen
    def closed_by_agent(ctx):
        fresh = real(ctx)
        store = fresh.store
        finish_run(store, store.runs()[0], store.load_card(cid), result="ok", usage=RunUsage(), note="", now=fresh.now)()
        return fresh
    monkeypatch.setattr(files, "reopen", closed_by_agent)
    assert apply_run.run_step(ctx_of(repo), h_with(s, run="run-ok"), dl.Log(s.root / "driver.log"), cid, 1) is False
    d = [x for x in s.decisions() if x.kind == "owner-action"][0]
    assert "pre-commit" in d.question and s.runs()[0].result == "ok"

def test_stuck_refuses_card_not_running(repo, capsys, monkeypatch, tmp_path):
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    assert apply_run.stuck(ctx_of(repo), dl.Log(s.root / "driver.log"), cid, None) is False
    assert s.load_card(cid).status == "ready" and not [x for x in s.decisions() if x.kind == "run-stuck"]

def test_accept_blocked_then_frame_outside_repo(repo, capsys, monkeypatch, tmp_path):
    from the_nod.driver import results
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    for step in (1, 2):
        apply_run.run_step(ctx_of(repo), h_with(s, run="run-ok"), dl.Log(s.root / "driver.log"), cid, step)
    monkeypatch.setattr(results, "read_accept", lambda path: results.AcceptResult(1, "unverified", blocked="no test mailbox"))
    assert apply_run.accept(ctx_of(repo), h_with(s, accept="accept-ok"), dl.Log(s.root / "driver.log"), cid) is False
    d = [x for x in s.decisions() if x.kind == "owner-action"][0]
    assert d.question == "no test mailbox" and s.load_acceptance(cid) is None and s.load_card(cid).status == "accepting"
    monkeypatch.setattr(results, "read_accept", lambda path: results.AcceptResult(2, "solved", frames=[("../x.png", "frame")]))
    assert apply_run.accept(ctx_of(repo), h_with(s, accept="accept-ok"), dl.Log(s.root / "driver.log"), cid) is False
    a = s.load_acceptance(cid)
    assert a.result == "unverified" and "frame outside the repo" in a.evidence and s.load_card(cid).status == "waiting-verdict"


def test_heartbeat_refusal_goes_to_log(repo, capsys, monkeypatch, tmp_path):
    from the_nod.gitsync import GitSync
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    monkeypatch.setattr(lock, "HEARTBEAT_SECONDS", 0.5)
    real_push, calls = GitSync.push, []

    def push(self):
        calls.append(1)
        return real_push(self) if len(calls) == 1 else False  # the lock is taken, the heartbeat is refused

    monkeypatch.setattr(GitSync, "push", push)
    apply_run.run_step(ctx_of(repo), h_with(s, run="run-slow"), dl.Log(s.root / "driver.log"), cid, 1)
    assert "heartbeat: push failed" in (s.root / "driver.log").read_text(encoding="utf-8")

def test_unrenderable_run_returns_card_without_run(repo, capsys, monkeypatch, tmp_path):
    import dataclasses
    from tests.conftest import git
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    s.save_card(dataclasses.replace(s.load_card(cid), brief="docs/missing.md"))
    git(repo, "commit", "-am", "state: broken brief")
    assert apply_run.run_step(ctx_of(repo), h_with(s, run="run-ok"), dl.Log(s.root / "driver.log"), cid, 1) is False
    d = [x for x in s.decisions() if x.kind == "return"][0]
    assert s.load_card(cid).status == "returned" and not s.runs()
    assert d.card == cid and "the run command is not built: invalid brief path" in d.reason and d.note == ""

def test_unrenderable_accept_is_unverified(repo, capsys, monkeypatch, tmp_path):
    import dataclasses
    from tests.conftest import git
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    s.save_card(dataclasses.replace(s.load_card(cid), status="accepting", brief="docs/missing.md"))
    git(repo, "commit", "-am", "state: broken brief")
    assert apply_run.accept(ctx_of(repo), h_with(s, accept="accept-ok"), dl.Log(s.root / "driver.log"), cid) is False
    a = s.load_acceptance(cid)
    assert a.result == "unverified" and "the acceptance command is not built" in a.evidence
    assert s.load_card(cid).status == "waiting-verdict"


def test_accept_records_spend(repo, capsys, monkeypatch, tmp_path):
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    for step in (1, 2):
        apply_run.run_step(ctx_of(repo), h_with(s, run="run-ok"), dl.Log(s.root / "driver.log"), cid, step)
    assert apply_run.accept(ctx_of(repo), h_with(s, accept="accept-ok"), dl.Log(s.root / "driver.log"), cid) is True
    # By kind, not by position: the files are sorted by name, `<second>-<kind>-<card>`, and a fast machine
    # writes the brief and the acceptance within one second.
    accepted = [spend for spend in s.spends() if spend.kind == "accept"]
    assert len(accepted) == 1 and accepted[0].card == cid

def test_run_step_closes_the_abandoned_run_of_its_card(repo, capsys, monkeypatch, tmp_path):
    from tests.conftest import git
    cid, s = ready_card(repo, capsys, monkeypatch, tmp_path)
    old = (main(["--root", str(repo), "run", "start", cid, "--step", "1"]), capsys.readouterr().out.strip())[1]
    card = s.load_card(cid); card.status = "ready"; s.save_card(card)  # an old state: returned, answered, the run stayed open
    git(repo, "commit", "-am", "state: abandoned run")
    assert apply_run.run_step(ctx_of(repo), h_with(s, run="run-ok"), dl.Log(s.root / "driver.log"), cid, 1) is True
    first, second = s.load_run(old), [r for r in s.runs() if r.id != old][0]
    assert first.result == "stop" and first.body == f"closed when run {second.id} started: the card was not running"
    assert second.result == "ok" and s.load_card(cid).steps[0].done and s.load_card(cid).status == "ready"
    assert "not started" not in (s.root / "driver.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("lang, note, why, owner", [
    ("en", "", "Why the card came back: stop: test", ""),
    ("en", "patch the test", "Why the card came back: stop: test", "Owner's note: patch the test"),
    ("ru", "", "Почему карточка вернулась: stop: test", ""),
])
def test_rerun_after_stop_shows_the_reason_apart_from_the_owner_note(repo, capsys, monkeypatch, tmp_path,
                                                                     lang, note, why, owner):
    """The field test: a stop note reached the repeat brief as "Owner's note" when the owner gave none."""
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys, lang=lang)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    log = dl.Log(s.root / "driver.log")
    from the_nod.driver import apply_brief
    apply_brief.brief(ctx_of(repo), h_with(s, brief="brief-ok"), log, cid)
    apply_run.run_step(ctx_of(repo), h_with(s, run="run-stop"), log, cid, 1)
    ret = [x for x in s.decisions() if x.kind == "return"][0]
    main(["--root", str(repo), "decision", "answer", ret.id, "rerun", *(["--note", note] if note else [])])
    react.react_with(ctx_of(repo), h_with(s, brief="brief-ok"), log, plan.reactions(s.cards(), s.decisions())[0])
    answers = files.answers_path(s, cid).read_text(encoding="utf-8")
    owner_label = {"en": "Owner's note:", "ru": "Замечание владельца:"}[lang]
    assert why in answers and f"{owner_label} stop: test" not in answers
    assert (owner in answers) if owner else owner_label not in answers
