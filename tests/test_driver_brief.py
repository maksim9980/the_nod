"""The brief executor: the agent command, forks for the owner, reactions, the guard of the command."""
import dataclasses
import sys
from pathlib import Path
from types import SimpleNamespace
from the_nod import context, harness
from the_nod.driver import apply_brief, log as dl, plan
from the_nod.store import Store
from tests.driver_helpers import env_for_tests, fake, setup
from tests.fake_agent import STEPS, TITLE
from the_nod.cli import main

def ctx_of(repo): return context.open(SimpleNamespace(root=str(repo)))
def go(repo, cid, mode, **kw):
    s = Store(repo / ".nod"); h = harness.load(s)
    h = harness.Harness(h.adapter, h.driver_host, {**h.commands, "brief": fake(mode)})
    return apply_brief.brief(ctx_of(repo), h, dl.Log(s.root / "driver.log"), cid, **kw)

def test_brief_without_forks_makes_ready(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    assert go(repo, cid, "brief-ok") is True
    c = s.load_card(cid)
    assert c.status == "ready" and c.brief == f"docs/briefs/{cid}.md" and [x.title for x in c.steps] == STEPS
    assert s.lock()["host"] == ctx_of(repo).host and (s.root / "driver" / f"{cid}.brief.prompt.md").exists()
    assert cid in (s.root / "driver" / f"{cid}.brief.prompt.md").read_text(encoding="utf-8")
    assert f"spend brief {cid}: tokens 0, minutes 0, $ —" in (s.root / "driver.log").read_text(encoding="utf-8")

def test_brief_with_forks_waits_owner(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    assert go(repo, cid, "brief-forks") is True
    d = [x for x in s.decisions() if x.kind == "fork"][0]
    assert s.load_card(cid).status == "waiting-owner" and d.card == cid
    assert d.question == "Keep history?" and d.proposed == "yes, 30 days" and d.options == ["yes, 30 days", "no", "forever"] and d.reason == "enough to debug"

def test_answers_decide_ready_or_rebrief(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    go(repo, cid, "brief-forks"); d = [x for x in s.decisions() if x.kind == "fork"][0]
    main(["--root", str(repo), "decision", "answer", d.id, "no", "--note", "no history needed"])
    action = plan.reactions(s.cards(), s.decisions())[0]
    h = harness.Harness("default", "", {**harness.load(s).commands, "brief": fake("brief-ok")})
    apply_brief.react_with(ctx_of(repo), h, dl.Log(s.root / "driver.log"), action)
    assert s.load_card(cid).status == "ready"
    answers = (s.root / "driver" / f"{cid}.answers.md").read_text(encoding="utf-8")
    assert "Keep history?" in answers and "Answer: no. no history needed" in answers

def test_all_proposed_goes_ready_without_rebrief(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    go(repo, cid, "brief-forks"); d = [x for x in s.decisions() if x.kind == "fork"][0]
    main(["--root", str(repo), "decision", "answer", d.id, "yes, 30 days"])
    h = harness.Harness("default", "", {**harness.load(s).commands, "brief": fake("brief-fail")})
    apply_brief.react_with(ctx_of(repo), h, dl.Log(s.root / "driver.log"), plan.reactions(s.cards(), s.decisions())[0])
    assert s.load_card(cid).status == "ready"

def test_failure_twice_returns_card(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    assert go(repo, cid, "brief-fail") is False and s.load_card(cid).status == "briefing"
    assert go(repo, cid, "brief-noresult") is False and s.load_card(cid).status == "returned"
    d = [x for x in s.decisions() if x.kind == "return"][0]
    assert d.card == cid and d.reason.startswith("brief failed:") and "no result file" in d.reason and d.note == ""
    assert "(1/2)" in (s.root / "driver.log").read_text(encoding="utf-8")

def test_garbage_section_ten_never_ready(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    go(repo, cid, "brief-garbage"); go(repo, cid, "brief-garbage")
    assert s.load_card(cid).status == "returned" and "no steps" in [x for x in s.decisions() if x.kind == "return"][0].reason

def test_blocked_and_auth_become_owner_action(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    assert go(repo, cid, "brief-blocked") is False
    d = [x for x in s.decisions() if x.kind == "owner-action"][0]
    assert d.question == "need an API key: put it into .env" and d.options == ["done", "postpone"] and d.card == cid
    assert s.load_card(cid).status == "briefing"
    main(["--root", str(repo), "decision", "answer", d.id, "done"])
    h = harness.Harness("default", "", {**harness.load(s).commands, "brief": fake("brief-ok")})
    apply_brief.react_with(ctx_of(repo), h, dl.Log(s.root / "driver.log"), plan.reactions(s.cards(), s.decisions())[0])
    assert "Consumed:" in s.load_decision(d.id).body and s.load_card(cid).status == "briefing"
    assert go(repo, cid, "brief-ok") is True and s.load_card(cid).status == "ready"
    cid2 = (main(["--root", str(repo), "card", "add", "Weekly email digest"]), capsys.readouterr().out.strip())[1]
    assert go(repo, cid2, "brief-auth") is False
    d2 = [x for x in s.decisions() if x.kind == "owner-action" and x.card == cid2][0]
    assert d2.question.startswith("Log in to claude") and "OAuth" in d2.question
    main(["--root", str(repo), "decision", "answer", d2.id, "postpone"])
    apply_brief.react(ctx_of(repo), dl.Log(s.root / "driver.log"), plan.reactions(s.cards(), s.decisions())[0])
    assert s.load_card(cid2).status == "backlog" and s.order()[-1] == cid2

def test_lock_lost_runs_nothing(repo, capsys, tmp_path, monkeypatch):
    from the_nod.gitsync import GitSync
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    monkeypatch.setattr(GitSync, "push", lambda self: False)
    assert go(repo, cid, "brief-ok") is False
    assert s.load_card(cid).status == "backlog" and not (s.root / "driver" / f"{cid}.brief.prompt.md").exists()

def test_next_batch_and_pain(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    ids = [(main(["--root", str(repo), "card", "add", t, "--source", "import"]), capsys.readouterr().out.strip())[1] for t in "ABCD"]
    did = apply_brief.ask_next_batch(ctx_of(repo), dl.Log(s.root / "driver.log"))
    d = s.load_decision(did)
    assert d.kind == "next-batch" and d.question == "Start the next batch? Cards: 3." and d.reason == "A; B; C" and all(f"- {i}  " in d.body for i in ids[:3])
    main(["--root", str(repo), "decision", "answer", did, "yes"])
    apply_brief.react(ctx_of(repo), dl.Log(s.root / "driver.log"), plan.reactions(s.cards(), s.decisions())[0])
    assert [s.load_card(i).status for i in ids] == ["briefing", "briefing", "briefing", "backlog"]
    pid = apply_brief.ask_pain(ctx_of(repo), dl.Log(s.root / "driver.log"))
    main(["--root", str(repo), "decision", "answer", pid, "Search on the site is slow\ndetails", "--free"])
    apply_brief.react(ctx_of(repo), dl.Log(s.root / "driver.log"), plan.reactions(s.cards(), s.decisions())[0])
    new = [c for c in s.cards() if c.title == "Search on the site is slow"][0]
    assert new.source == "owner" and s.order()[0] == new.id and f"Card: {new.id}" in s.load_decision(pid).body


# --- behaviour from the controller rulings that the brief tests did not cover ---

def test_hooks_tampering_becomes_owner_action(repo, capsys, tmp_path, monkeypatch):
    from the_nod.driver import agent
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    snapshots = iter([{}, {"pre-commit": "abc"}])
    monkeypatch.setattr(agent, "hooks_snapshot", lambda folder: next(snapshots))
    assert go(repo, cid, "brief-ok") is False
    d = [x for x in s.decisions() if x.kind == "owner-action"][0]
    assert d.question == "the agent changed .git/hooks or the git config: pre-commit — check and delete"
    assert d.card == cid and d.reason == "the brief command waits for an owner action"
    c = s.load_card(cid)
    assert c.status == "briefing" and c.brief is None and c.steps == []

def test_stale_after_command_writes_nothing(repo, capsys, tmp_path, monkeypatch):
    import dataclasses
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    monkeypatch.setattr(apply_brief.files, "reopen",
                        lambda ctx: dataclasses.replace(ctx_of(repo), fresh=False, stale_since="2026-10-21T10:00:00"))
    assert go(repo, cid, "brief-ok") is False
    c = s.load_card(cid)
    assert c.status == "briefing" and c.steps == []
    log = (s.root / "driver.log").read_text(encoding="utf-8")
    assert f"ERROR the state is stale: the brief result of {cid} is not written, file" in log
    assert f"{cid}.brief.toml" in log

def test_rebrief_answers_survive_failed_attempt(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    go(repo, cid, "brief-forks"); d = [x for x in s.decisions() if x.kind == "fork"][0]
    main(["--root", str(repo), "decision", "answer", d.id, "no"])
    h = harness.Harness("default", "", {**harness.load(s).commands, "brief": fake("brief-fail")})
    apply_brief.react_with(ctx_of(repo), h, dl.Log(s.root / "driver.log"), plan.reactions(s.cards(), s.decisions())[0])
    assert s.load_card(cid).status == "briefing" and "Consumed:" in s.load_decision(d.id).body
    assert plan.reactions(s.cards(), s.decisions()) == []
    assert go(repo, cid, "brief-ok") is True
    assert "Answer: no." in (s.root / "driver" / f"{cid}.answers.md").read_text(encoding="utf-8")


# --- review fixes: one reaction per decision, answers per cycle, the brief path ---

from the_nod.driver import files, react  # noqa: E402

def test_second_fork_action_is_noop(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    go(repo, cid, "brief-forks")
    main(["--root", str(repo), "decision", "ask", "--kind", "fork", "--question", "Second?", "--proposed", "A",
          "--option", "A", "--option", "B", "--card", cid]); capsys.readouterr()
    first, second = sorted((x for x in s.decisions() if x.kind == "fork"), key=lambda x: x.question != "Keep history?")
    main(["--root", str(repo), "decision", "answer", first.id, "no"])
    main(["--root", str(repo), "decision", "answer", second.id, "A"])
    actions = plan.reactions(s.cards(), s.decisions())
    assert len(actions) == 2
    h = harness.Harness("default", "", {**harness.load(s).commands, "brief": fake("brief-forks")})
    log = dl.Log(s.root / "driver.log")
    react.react_with(ctx_of(repo), h, log, actions[0])
    assert s.load_card(cid).status == "waiting-owner"
    react.react_with(ctx_of(repo), h, log, actions[1])
    assert s.load_card(cid).status == "waiting-owner"
    assert [s.load_decision(x.id).body.count("Consumed:") for x in (first, second)] == [1, 1]

def _returned_after_rebrief(repo, capsys, s):
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    go(repo, cid, "brief-forks"); d = [x for x in s.decisions() if x.kind == "fork"][0]
    main(["--root", str(repo), "decision", "answer", d.id, "no", "--note", "no history needed"])
    h = harness.Harness("default", "", {**harness.load(s).commands, "brief": fake("brief-fail")})
    react.react_with(ctx_of(repo), h, dl.Log(s.root / "driver.log"), plan.reactions(s.cards(), s.decisions())[0])
    go(repo, cid, "brief-fail")
    assert s.load_card(cid).status == "returned"
    return cid, [x for x in s.decisions() if x.kind == "return"][0]

def test_rerun_keeps_fork_answers(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid, ret = _returned_after_rebrief(repo, capsys, s)
    main(["--root", str(repo), "decision", "answer", ret.id, "rerun", "--note", "check again"])
    h = harness.Harness("default", "", {**harness.load(s).commands, "brief": fake("brief-ok")})
    react.react_with(ctx_of(repo), h, dl.Log(s.root / "driver.log"), plan.reactions(s.cards(), s.decisions())[0])
    assert s.load_card(cid).status == "ready"
    answers = files.answers_path(s, cid).read_text(encoding="utf-8")
    assert "Answer: no. no history needed" in answers and "Owner's note: brief failed" not in answers
    assert "Owner's note: check again" in answers and "No answers." not in answers

def test_backlog_forgets_cycle(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid, ret = _returned_after_rebrief(repo, capsys, s)
    files.bump_attempt(s, cid)
    main(["--root", str(repo), "decision", "answer", ret.id, "backlog"])
    react.react(ctx_of(repo), dl.Log(s.root / "driver.log"), plan.reactions(s.cards(), s.decisions())[0])
    assert s.load_card(cid).status == "backlog" and s.order()[-1] == cid
    assert not files.answers_path(s, cid).exists() and cid not in files.attempts(s)

def _bad_result_command(tmp_path, value):
    script = tmp_path / "bad_result.py"
    script.write_text("import os\nopen(os.environ['NOD_RESULT'], 'w', encoding='utf-8').write(%r)\n" % f'brief = "{value}"\n', encoding="utf-8")
    return f'"{sys.executable}" "{script}"'

def test_unsafe_brief_path_from_result_fails(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    (repo / "docs").mkdir(); (repo / "docs" / "x.md").write_text("# x\n", encoding="utf-8"); (repo.parent / "x.md").write_text("# x\n", encoding="utf-8")
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    log = dl.Log(s.root / "driver.log")
    for value in ("docs/x.md; echo pwned", "../x.md"):
        h = harness.Harness("default", "", {**harness.load(s).commands, "brief": _bad_result_command(tmp_path, value)})
        assert apply_brief.brief(ctx_of(repo), h, log, cid) is False
        assert f"invalid brief path: {value}" in (s.root / "driver.log").read_text(encoding="utf-8")
        assert s.load_card(cid).brief is None
    assert s.load_card(cid).status == "returned"
    assert [x for x in s.decisions() if x.kind == "return"][0].reason == "brief failed: invalid brief path: ../x.md"

def test_unsafe_card_brief_launches_nothing(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    s.save_card(dataclasses.replace(s.load_card(cid), brief="docs/x.md; echo pwned"))
    assert go(repo, cid, "brief-ok") is False
    assert "ERROR brief" in (s.root / "driver.log").read_text(encoding="utf-8")
    assert not files.prompt_path(s, cid, "brief").exists() and s.load_card(cid).status == "backlog"

def test_command_values_reject_shell_characters():
    base = {k: "x" for k in harness.PLACEHOLDERS}
    assert files.command_values({**base, "root": r"C:\Мой репо\x", "title": 'a"b'})["root"] == r"C:\Мой репо\x"
    for bad in ('a"b', "a'b", "a;b", "a&b", "a|b", "a`b", "a$b", "a\nb", "a\rb", "a\x01b"):
        try:
            files.command_values({**base, "result": bad})
        except harness.HarnessError as err:
            assert str(err) == "invalid character in placeholder {result}"
        else:
            raise AssertionError(bad)

def test_owner_change_during_brief_keeps_result(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    real = apply_brief.files.reopen
    def reopen(ctx):
        main(["--root", str(repo), "card", "close", cid])
        return real(ctx)
    monkeypatch.setattr(apply_brief.files, "reopen", reopen)
    assert go(repo, cid, "brief-ok") is False
    assert s.load_card(cid).status == "done" and files.result_path(s, cid, "brief").exists()
    assert f"card {cid} changed during the brief: done, the result is not written" in (s.root / "driver.log").read_text(encoding="utf-8")

def test_next_batch_without_candidates_writes_nothing(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    assert react.ask_next_batch(ctx_of(repo), dl.Log(s.root / "driver.log")) == "" and s.decisions() == []


# --- final wave: the manifest, backslashes, the spend ---

def test_manifest_change_without_origin_becomes_owner_action(repo, capsys, tmp_path, monkeypatch):
    from the_nod.driver import guard
    from tests.conftest import git
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    git(repo, "remote", "remove", "origin")
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    shas = iter(["before", "after"])
    monkeypatch.setattr(guard, "manifest_sha", lambda ctx: next(shas))
    assert go(repo, cid, "brief-ok") is False
    d = [x for x in s.decisions() if x.kind == "owner-action"][0]
    assert d.question == "the agent changed harness.toml — the version from the snapshot before the command is restored, check" and d.card == cid
    assert s.load_card(cid).status == "briefing" and s.load_card(cid).brief is None
    assert f"state: driver restore harness.toml {cid}" in git(repo, "log", "-5", "--format=%s").splitlines()

def test_manifest_change_restored_from_origin(repo, capsys, tmp_path, monkeypatch):
    from the_nod.driver import agent
    from tests.conftest import git
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    manifest_file = s.root / "harness.toml"

    def tamper(command, *, cwd, env, **kw):
        manifest_file.write_text(manifest_file.read_text(encoding="utf-8") + "# agent\n", encoding="utf-8")
        git(repo, "commit", "-qam", "agent edits the manifest")
        (repo / "docs").mkdir(exist_ok=True)
        (repo / "docs" / "b.md").write_text("# b\n", encoding="utf-8")
        Path(env["NOD_RESULT"]).write_text('brief = "docs/b.md"\n', encoding="utf-8")
        return agent.Outcome("exit", 0, "", "", 1)

    monkeypatch.setattr(agent, "run_command", tamper)
    assert go(repo, cid, "brief-ok") is False
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    origin = git(repo, "show", f"origin/{branch}:.nod/harness.toml")
    assert manifest_file.read_text(encoding="utf-8").replace("\r\n", "\n") == origin.replace("\r\n", "\n")
    assert "# agent" not in manifest_file.read_text(encoding="utf-8")
    d = [x for x in s.decisions() if x.kind == "owner-action"][0]
    assert d.question == "the agent changed harness.toml — the origin version is restored, check"
    assert s.load_card(cid).status == "briefing" and s.load_card(cid).brief is None
    assert git(repo, "status", "--porcelain", "--", ".nod/harness.toml").strip() == ""

def test_brief_path_accepts_backslashes(tmp_path):
    (tmp_path / "docs" / "briefs").mkdir(parents=True)
    (tmp_path / "docs" / "briefs" / "x.md").write_text("# x\n", encoding="utf-8")
    assert files.brief_path(tmp_path, "docs\\briefs\\x.md") == "docs/briefs/x.md"

def test_fork_answers_do_not_double_period():
    d = SimpleNamespace(question="Keep?", answer="no.", note="")
    assert apply_brief.fork_answers([d]) == ["1. Keep?\n   Answer: no."]

def test_shell_unsafe_includes_redirects():
    base = {k: "x" for k in harness.PLACEHOLDERS}
    for bad in ("a<b", "a>b", "a^b"):
        try:
            files.command_values({**base, "result": bad})
        except harness.HarnessError:
            continue
        raise AssertionError(bad)
    assert files.command_values({**base, "root": r"C:\Program Files (x86)\x%y!"})["root"].endswith("x%y!")


# --- the guard: the hooks folder and the state ---

def _patched(monkeypatch, action):
    from the_nod.driver import agent

    def command(cmd, *, cwd, env, **kw):
        action(Path(cwd), env)
        return agent.Outcome("exit", 0, "", "", 1)

    monkeypatch.setattr(agent, "run_command", command)

def test_hook_dropped_into_hooks_folder_is_removed(repo, capsys, tmp_path, monkeypatch):
    from the_nod.driver import guard
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    folder = guard.hooks_dir(repo)
    assert folder.parent.name == ".git" and folder.name == "nod-no-hooks"
    _patched(monkeypatch, lambda root, env: (folder.mkdir(parents=True, exist_ok=True),
                                              (folder / "pre-commit").write_text("echo pwned\n", encoding="utf-8")))
    assert go(repo, cid, "brief-ok") is False
    d = [x for x in s.decisions() if x.kind == "owner-action"][0]
    assert d.question == "the agent put hooks into the driver folder — check" and d.card == cid
    assert list(folder.iterdir()) == [] and s.load_card(cid).status == "briefing"
    assert "ERROR the agent put files into the hooks folder" in (s.root / "driver.log").read_text(encoding="utf-8")

def test_extra_card_file_is_removed(repo, capsys, tmp_path, monkeypatch):
    from tests.conftest import git
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    extra = repo / ".nod" / "cards" / "c-zzzz-agent.md"
    _patched(monkeypatch, lambda root, env: extra.write_text("+++\nid = \"c-zzzz\"\n+++\n", encoding="utf-8"))
    assert go(repo, cid, "brief-ok") is False
    d = [x for x in s.decisions() if x.kind == "owner-action"][0]
    assert d.question == "the agent changed the .nod state — restored, check"
    assert not extra.exists() and s.load_card(cid).status == "briefing"
    assert f"state: driver restore state {cid}" in git(repo, "log", "-5", "--format=%s").splitlines()
    assert git(repo, "status", "--porcelain", "--", ".nod/cards").strip() == ""

def test_uncommitted_card_edit_is_restored(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    path = next((repo / ".nod" / "cards").glob(f"{cid}*.md"))
    _patched(monkeypatch, lambda root, env: path.write_text(
        path.read_text(encoding="utf-8").replace("briefing", "done"), encoding="utf-8"))
    assert go(repo, cid, "brief-ok") is False
    assert s.load_card(cid).status == "briefing"
    assert [x for x in s.decisions() if x.kind == "owner-action"][0].question.startswith("the agent changed the .nod state")

def test_normal_brief_leaves_guard_quiet(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    assert go(repo, cid, "brief-ok") is True
    assert not [x for x in s.decisions() if x.kind == "owner-action"]

def test_edited_wrapper_is_rewritten_before_the_next_command(repo, capsys, tmp_path, monkeypatch):
    """The `nod` wrapper heads the agent's PATH: one left edited by an earlier command does not run again."""
    from the_nod.driver import files as driver_files, shim
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    folder = shim.bin_dir(s)
    folder.mkdir(parents=True)
    for name in ("nod", "nod.cmd"):
        (folder / name).write_text("echo pwned\n", encoding="utf-8")
    go(repo, cid, "nod")
    out = driver_files.output_paths(s, cid, "brief")[0].read_text(encoding="utf-8")
    assert "usage: nod" in out and "pwned" not in out
    assert (folder / "nod").read_text(encoding="utf-8").startswith("#!/bin/sh\n")

def test_stale_after_restore_is_logged(repo, capsys, tmp_path, monkeypatch):
    from the_nod.driver import files as driver_files
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    extra = repo / ".nod" / "cards" / "c-zzzz-agent.md"
    _patched(monkeypatch, lambda root, env: extra.write_text("x\n", encoding="utf-8"))
    real = driver_files.reopen
    monkeypatch.setattr(driver_files, "reopen", lambda ctx: dataclasses.replace(real(ctx), fresh=False, stale_since="t"))
    assert go(repo, cid, "brief-ok") is False
    text = (s.root / "driver.log").read_text(encoding="utf-8")
    assert "the restore of the .nod state is not committed: the state is stale, the file is restored locally" in text
    assert not extra.exists()

def test_guard_state_error_is_fail_closed(repo, capsys, tmp_path, monkeypatch):
    from the_nod.driver import guard
    from the_nod.gitsync import GitError
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    manifest_checked = []
    real_restore = guard.restore_manifest

    def dirty_fails(ctx):
        raise GitError("git status: failure")

    def restore_manifest(ctx, ref):
        manifest_checked.append(1)
        return real_restore(ctx, ref)

    monkeypatch.setattr(guard, "_dirty_paths", dirty_fails)
    monkeypatch.setattr(guard, "restore_manifest", restore_manifest)
    assert go(repo, cid, "brief-ok") is False
    assert manifest_checked == [1]
    assert not [x for x in s.decisions() if x.kind == "owner-action"]  # not checked: nothing is written
    text = (s.root / "driver.log").read_text(encoding="utf-8")
    assert "ERROR the check of the .nod state failed: git status: failure" in text
    assert "the owner decision is not written" in text
    assert apply_brief.unwritable(dl.Log(s.root / "driver.log"), [guard.STATE_FAILED]) is True

def test_card_hidden_by_agent_gitignore_is_removed(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    cards = repo / ".nod" / "cards"
    ignore, fake_card = cards / ".gitignore", cards / "c-zzzz-agent.md"

    def hide(root, env):
        ignore.write_text("*\n", encoding="utf-8")
        fake_card.write_text("+++\nid = \"c-zzzz\"\n+++\n", encoding="utf-8")

    _patched(monkeypatch, hide)
    assert go(repo, cid, "brief-ok") is False
    assert not ignore.exists() and not fake_card.exists()
    d = [x for x in s.decisions() if x.kind == "owner-action"][0]
    assert d.question == "the agent changed the .nod state — restored, check"

def test_failed_rollback_writes_nothing(repo, capsys, tmp_path, monkeypatch):
    import subprocess
    from the_nod.driver import guard
    from tests.conftest import git
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    path = next((repo / ".nod" / "cards").glob(f"{cid}*.md"))
    _patched(monkeypatch, lambda root, env: path.write_text(
        path.read_text(encoding="utf-8").replace("briefing", "done"), encoding="utf-8"))
    real_git = guard._git

    def git_without_checkout(root, *args):
        if args and args[0] == "checkout":
            return subprocess.CompletedProcess(["git", *args], 1, "", "index.lock is busy")
        return real_git(root, *args)

    monkeypatch.setattr(guard, "_git", git_without_checkout)
    assert go(repo, cid, "brief-ok") is False
    # no commit after the claim: a write would commit the agent edit
    assert git(repo, "log", "-1", "--format=%s").strip() == f"state: driver brief {cid} briefing"
    assert not [x for x in s.decisions() if x.kind == "owner-action"]
    text = (s.root / "driver.log").read_text(encoding="utf-8")
    assert "ERROR the state is not restored: .nod/cards/" in text
    assert "the owner decision is not written" in text
    assert "done" in path.read_text(encoding="utf-8")

def test_clear_hooks_removes_link_without_following(tmp_path):
    import os
    import subprocess
    from the_nod.driver import guard
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("x", encoding="utf-8")
    folder = tmp_path / "git" / "nod-no-hooks"
    folder.parent.mkdir()
    try:
        if os.name == "nt":
            done = subprocess.run(["cmd", "/c", "mklink", "/J", str(folder), str(outside)], capture_output=True)
            if done.returncode != 0:
                import pytest
                pytest.skip("cannot create a junction")
        else:
            os.symlink(outside, folder, target_is_directory=True)
    except PermissionError:
        import pytest
        pytest.skip("cannot create a link")
    assert guard.clear_hooks(folder) is True
    assert (outside / "keep.txt").exists()
    assert folder.is_dir() and not guard.is_link(folder) and list(folder.iterdir()) == []

def test_clear_hooks_removes_inner_link_only(tmp_path):
    import os
    import subprocess
    from the_nod.driver import guard
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("x", encoding="utf-8")
    folder = tmp_path / "nod-no-hooks"
    folder.mkdir()
    inner = folder / "pre-commit.d"
    try:
        if os.name == "nt":
            done = subprocess.run(["cmd", "/c", "mklink", "/J", str(inner), str(outside)], capture_output=True)
            if done.returncode != 0:
                import pytest
                pytest.skip("cannot create a junction")
        else:
            os.symlink(outside, inner, target_is_directory=True)
    except PermissionError:
        import pytest
        pytest.skip("cannot create a link")
    assert guard.clear_hooks(folder) is True
    assert (outside / "keep.txt").exists() and list(folder.iterdir()) == []


def test_brief_records_spend(repo, capsys, tmp_path, monkeypatch):
    from tests.conftest import git
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    assert go(repo, cid, "brief-ok") is True
    spent = s.spends()
    assert len(spent) == 1 and spent[0].kind == "brief" and spent[0].card == cid
    assert f"state: driver usage brief {cid}" in git(repo, "log", "--format=%s", "-5")


def test_failed_brief_still_records_spend(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = (main(["--root", str(repo), "card", "add", TITLE]), capsys.readouterr().out.strip())[1]
    assert go(repo, cid, "brief-fail") is False
    assert [x.kind for x in s.spends()] == ["brief"]


# --- message keys held in tables, out of reach of the literal-key scan in tests/test_i18n.py ---

def test_key_tables_exist_in_both_languages():
    from the_nod import i18n
    from the_nod.driver import guard
    keys = {*apply_brief.KIND_KEYS.values(), *guard.TEXT_KEYS.values(), *guard._LABEL_KEYS.values()}
    for lang in i18n.LANGS:
        assert sorted(keys - i18n.catalog(lang).keys()) == [], lang


def test_guard_labels_follow_language():
    from the_nod import i18n
    from the_nod.driver import guard
    assert [guard.label(n) for n in (guard.STATE, guard.MANIFEST_LOCAL, "pre-commit")] == \
        ["the .nod state", "harness.toml", "pre-commit"]
    i18n.use("ru")
    assert guard.label(guard.HOOKS) == "папки хуков" and guard.label(guard.GIT_CONFIG) == "конфиг git"
    assert apply_brief.kind_name("accept") == "приёмка" and apply_brief.kind_name("other") == "other"
