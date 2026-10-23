"""`nod card return` closes the open run of the card, in the commit that returns it."""
from the_nod.cli import main
from the_nod.driver import apply_run, log as dl
from the_nod.model import Step
from the_nod.store import Store
from tests.conftest import git
from tests.driver_helpers import add_card, driver_run, env_for_tests, setup
from tests.test_driver_run import ctx_of, h_with

NOTE = "wrong date format"


def cli(repo, *args, capsys):
    code = main(["--root", str(repo), *args])
    out = capsys.readouterr()
    return code, out.out, out.err


def seeded(repo, capsys, title="Export habits to CSV"):
    cli(repo, "init", capsys=capsys)
    cid = cli(repo, "card", "add", title, capsys=capsys)[1].strip()
    store = Store(repo / ".nod")
    card = store.load_card(cid)
    card.status, card.steps = "ready", [Step(1, "Write the export"), Step(2, "Add a menu item")]
    store.save_card(card)
    git(repo, "commit", "-am", "state: ready")
    return cid, store


def start_run(repo, cid, *, capsys) -> str:
    return cli(repo, "run", "start", cid, "--step", "1", "--contracts", "3", capsys=capsys)[1].strip()


def commit_count(repo) -> int:
    return int(git(repo, "rev-list", "--count", "HEAD").strip())


def test_return_closes_the_open_run_in_one_commit(repo, capsys):
    cid, s = seeded(repo, capsys)
    rid = start_run(repo, cid, capsys=capsys)
    cli(repo, "run", "progress", rid, "--contracts-done", "2", capsys=capsys)
    before = commit_count(repo)
    assert cli(repo, "card", "return", cid, "--note", NOTE, capsys=capsys)[0] == 0
    run = s.load_run(rid)
    assert run.finished is not None and run.result == "stop"
    assert run.body.endswith("\n" + NOTE) and run.contracts_done == 2
    assert s.load_card(cid).status == "returned"
    decision = s.decisions()[0]
    assert (decision.kind, decision.card, decision.note) == ("return", cid, NOTE)
    assert commit_count(repo) == before + 1
    assert git(repo, "log", "-1", "--format=%s").strip() == f"state: card return {cid}"
    touched = git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert sorted(f.split("/")[1] for f in touched) == ["cards", "decisions", "runs"], touched
    assert git(repo, "status", "--porcelain", "--", ".nod").strip() == ""


def test_return_keeps_the_answers_to_the_decision_as_before(repo, capsys):
    cid, s = seeded(repo, capsys)
    start_run(repo, cid, capsys=capsys)
    cli(repo, "card", "return", cid, "--note", NOTE, capsys=capsys)
    decision = s.decisions()[0]
    assert decision.proposed == "rerun" and decision.options == ["rerun", "backlog"]
    assert cli(repo, "decision", "answer", decision.id, "backlog", capsys=capsys)[0] == 0
    assert s.load_run(s.runs()[0].id).result == "stop"


def test_return_without_an_open_run_writes_no_run(repo, capsys):
    cid, s = seeded(repo, capsys)
    cli(repo, "card", "return", cid, "--note", NOTE, capsys=capsys)
    assert s.runs() == [] and s.load_card(cid).status == "returned"
    touched = set(git(repo, "show", "--name-only", "--format=", "HEAD").split())
    assert not [f for f in touched if "/runs/" in f]


def test_return_leaves_a_finished_run_alone(repo, capsys):
    cid, s = seeded(repo, capsys)
    rid = start_run(repo, cid, capsys=capsys)
    cli(repo, "run", "finish", rid, "--result", "ok", "--note", "step one done", capsys=capsys)
    finished = s.load_run(rid)
    cli(repo, "card", "return", cid, "--note", NOTE, capsys=capsys)
    assert s.load_run(rid) == finished


def test_finish_after_return_is_refused_in_both_languages(repo, capsys, monkeypatch):
    cid, s = seeded(repo, capsys)
    rid = start_run(repo, cid, capsys=capsys)
    cli(repo, "card", "return", cid, "--note", NOTE, capsys=capsys)
    code, _, err = cli(repo, "run", "finish", rid, "--result", "ok", capsys=capsys)
    assert code == 2 and "already finished" in err
    monkeypatch.setenv("NOD_LANG", "ru")
    code, _, err = cli(repo, "run", "finish", rid, "--result", "ok", capsys=capsys)
    assert code == 2 and "уже завершён" in err
    assert s.load_run(rid).result == "stop"


def test_after_return_and_backlog_answer_the_driver_runs_another_card(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    first = add_card(repo, capsys, "Export habits to CSV")
    second = add_card(repo, capsys, "Weekly email digest")
    for cid in (first, second):
        card = s.load_card(cid)
        card.status, card.steps = "ready", [Step(1, "Write the code")]
        s.save_card(card)
    git(repo, "commit", "-am", "state: ready")
    start_run(repo, first, capsys=capsys)
    cli(repo, "card", "return", first, "--note", NOTE, capsys=capsys)
    decision = s.decisions()[0]
    cli(repo, "decision", "answer", decision.id, "backlog", capsys=capsys)
    code, out, _ = driver_run(repo, "once", capsys=capsys)
    assert code == 0 and out.startswith(f"run: run {second}")
    assert s.load_card(first).status == "backlog"
    assert {r.card for r in s.runs()} == {first, second} and all(r.finished for r in s.runs())


def test_owner_return_during_a_driver_run_keeps_the_stop(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    card = s.load_card(cid)
    card.status, card.steps = "ready", [Step(1, "Write the code")]
    s.save_card(card)
    git(repo, "commit", "-am", "state: ready")
    real = apply_run.files.reopen

    def reopen(ctx):
        cli(repo, "card", "return", cid, "--note", NOTE, capsys=capsys)
        return real(ctx)

    monkeypatch.setattr(apply_run.files, "reopen", reopen)
    log = dl.Log(s.root / "driver.log")
    assert apply_run.run_step(ctx_of(repo), h_with(s, run="run-ok"), log, cid, 1) is False
    run = s.runs()[0]
    assert run.result == "stop" and run.body == NOTE and run.contracts_done == 0
    assert s.load_card(cid).status == "returned" and not s.load_card(cid).steps[0].done
    text = (s.root / "driver.log").read_text(encoding="utf-8")
    assert f"run {run.id} changed during the command: card returned, the result is not written" in text
    assert "Traceback" not in text

def test_return_saves_the_card_once_as_returned(repo, capsys, monkeypatch):
    cid, s = seeded(repo, capsys)
    start_run(repo, cid, capsys=capsys)
    saved, real = [], Store.save_card
    monkeypatch.setattr(Store, "save_card", lambda self, card: (saved.append(card.status), real(self, card))[1])
    cli(repo, "card", "return", cid, "--note", NOTE, capsys=capsys)
    assert saved == ["returned"]


def test_driver_closes_the_old_run_of_a_ready_card_that_is_first_in_order(repo, capsys, monkeypatch, tmp_path):
    # an old state: the card was returned, answered and became ready again while its run stayed open
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    first = add_card(repo, capsys, "Export habits to CSV")
    waiting = add_card(repo, capsys, "Dark mode for the habit grid")
    other = add_card(repo, capsys, "Weekly email digest")
    for cid in (first, other):
        card = s.load_card(cid)
        card.status, card.steps = "ready", [Step(1, "Write the code")]
        s.save_card(card)
    git(repo, "commit", "-am", "state: ready")
    old = start_run(repo, first, capsys=capsys)
    card = s.load_card(first)
    card.status = "ready"
    s.save_card(card)
    git(repo, "commit", "-am", "state: abandoned run")
    code, out, _ = driver_run(repo, "once", capsys=capsys)
    assert code == 0 and out.startswith(f"run: run {first}")
    runs = [r for r in s.runs() if r.card == first]
    new = next(r for r in runs if r.id != old)
    assert s.load_run(old).result == "stop" and new.id in s.load_run(old).body and new.result == "ok"
    assert not [r for r in s.runs() if r.card == other] and s.load_card(waiting).status == "backlog"
    assert "not started" not in (s.root / "driver.log").read_text(encoding="utf-8")
