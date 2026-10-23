"""`nod driver once`: one pass through the CLI, its one-line result and the project language."""
import re

import pytest

from the_nod.cli import main
from tests.driver_helpers import add_card, driver_run, env_for_tests, setup

CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def without_paths(text: str, root) -> str:
    """`text` without the test folder in any spelling: a temp folder may hold a non-English user name."""
    for form in {str(root), str(root.resolve()), root.as_posix(), root.resolve().as_posix()}:
        text = text.replace(form, "<tmp>")
    return text


def full_cycle(repo, capsys, s, cid, *, fork_answer: str) -> None:
    """Brief with a fork, the answer, two run steps, the acceptance, the verdict and the pain question."""
    assert driver_run(repo, "once", capsys=capsys)[1].startswith("brief:") and s.load_card(cid).status == "waiting-owner"
    assert driver_run(repo, "once", capsys=capsys)[1].startswith("idle:") and s.load_card(cid).status == "waiting-owner"
    fork = [d for d in s.decisions() if d.kind == "fork"][0]
    main(["--root", str(repo), "decision", "answer", fork.id, fork_answer])
    assert driver_run(repo, "once", capsys=capsys)[1].startswith("react:") and s.load_card(cid).status == "ready"
    assert driver_run(repo, "once", capsys=capsys)[1].startswith("run:") and s.load_card(cid).steps[0].done
    assert s.load_card(cid).status == "ready"
    assert driver_run(repo, "once", capsys=capsys)[1].startswith("run:") and s.load_card(cid).status == "accepting"
    assert driver_run(repo, "once", capsys=capsys)[1].startswith("accept:") and s.load_card(cid).status == "waiting-verdict"
    verdict = [d for d in s.decisions() if d.kind == "verdict"][0]
    main(["--root", str(repo), "decision", "answer", verdict.id, "accept"])
    assert s.load_card(cid).status == "done" and driver_run(repo, "once", capsys=capsys)[1].startswith("pain:")


def test_once_full_cycle(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys, brief="brief-forks-then-ok")
    cid = add_card(repo, capsys)
    full_cycle(repo, capsys, s, cid, fork_answer="no")
    assert [d for d in s.decisions() if d.kind == "pain"]

def test_once_stale_and_foreign(repo, capsys, monkeypatch, tmp_path):
    from the_nod.gitsync import GitSync
    from datetime import datetime, timedelta
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    at = (datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
    s.write_lock("laptop", at)
    code, out, _ = driver_run(repo, "once", capsys=capsys)
    assert code == 0 and out.strip() == f"foreign: work in progress on laptop since {at}"
    monkeypatch.setattr(GitSync, "pull_ff", lambda self: False)
    code, out, _ = driver_run(repo, "once", capsys=capsys)
    assert code == 3 and out.startswith("stale: the state has been stale since ")

def test_once_refuses_other_driver_host(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    p = s.root / "harness.toml"; p.write_text(p.read_text(encoding="utf-8").replace('driver_host = ""', 'driver_host = "desktop"'), encoding="utf-8")
    code, _, err = driver_run(repo, "once", capsys=capsys)
    assert code == 2 and "the driver of this project runs on desktop" in err

def test_once_survives_action_error(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys, brief="no-such-mode")
    add_card(repo, capsys)
    code, out, _ = driver_run(repo, "once", capsys=capsys)
    assert code == 0 and out.startswith("brief:") and "ERROR" not in out
    assert "failed (1/2)" in (s.root / "driver.log").read_text(encoding="utf-8")

def test_once_busy_when_pid_alive(repo, capsys, monkeypatch, tmp_path):
    import subprocess, sys
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    pid_file = s.root / "driver" / "pid"; pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(other.pid), encoding="utf-8")
    try:
        code, out, _ = driver_run(repo, "once", capsys=capsys)
    finally:
        other.kill(); other.wait()
    assert code == 0 and out.strip() == f"busy: the driver is already running (pid {other.pid})"
    assert pid_file.read_text(encoding="utf-8").strip() == str(other.pid)

def test_once_lock_lost_when_push_fails(repo, capsys, monkeypatch, tmp_path):
    from the_nod.gitsync import GitSync
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    monkeypatch.setattr(GitSync, "push", lambda self: False)
    code, out, _ = driver_run(repo, "once", capsys=capsys)
    assert code == 0 and out.strip() == "lock-lost: push failed"
    assert s.load_card(cid).status == "backlog" and not (s.root / "driver" / "pid").exists()

def test_once_corrupt_state_is_error(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    (s.root / "cards").mkdir(parents=True, exist_ok=True)
    (s.root / "cards" / "c-bad.md").write_text("+++\nid = \n+++\n", encoding="utf-8")
    from tests.conftest import git
    git(repo, "add", ".nod/cards/c-bad.md")
    git(repo, "commit", "-m", "state: broken card")  # an uncommitted one is lock-lost, not error
    code, out, _ = driver_run(repo, "once", capsys=capsys)
    assert code == 0 and out.startswith("error: ")
    assert not (s.root / "driver" / "pid").exists()
    assert "ERROR pass aborted" in (s.root / "driver.log").read_text(encoding="utf-8")


def test_once_failed_rebrief_is_not_success(repo, capsys, monkeypatch, tmp_path):
    from the_nod.driver import react
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys, brief="brief-forks")
    cid = add_card(repo, capsys)
    assert driver_run(repo, "once", capsys=capsys)[1].startswith("brief:")
    fork = [d for d in s.decisions() if d.kind == "fork"][0]
    main(["--root", str(repo), "decision", "answer", fork.id, "no"]); capsys.readouterr()
    monkeypatch.setattr(react, "brief", lambda *a, **k: False)
    assert driver_run(repo, "once", capsys=capsys)[1].strip() == f"react: react {cid}: failed, see driver.log"

def test_once_unrenderable_brief_does_not_lock_queue(repo, capsys, monkeypatch, tmp_path):
    import dataclasses
    from tests.conftest import git
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    bad = add_card(repo, capsys, "Weekly email digest")
    good = add_card(repo, capsys, "Dark mode for the habit grid")
    s.save_card(dataclasses.replace(s.load_card(bad), brief="docs/missing.md"))
    git(repo, "commit", "-am", "state: broken brief")
    for _ in range(2):
        assert driver_run(repo, "once", capsys=capsys)[1].startswith(f"brief: brief {bad}: failed")
    assert s.load_card(bad).status == "returned"
    d = [x for x in s.decisions() if x.kind == "return"][0]
    assert d.card == bad and "invalid brief path" in d.reason and d.note == ""
    assert driver_run(repo, "once", capsys=capsys)[1].strip() == f"brief: brief {good}"

def test_once_dirty_state_blocks_reactions(repo, capsys, monkeypatch, tmp_path):
    from tests.conftest import git
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys, brief="brief-forks")
    add_card(repo, capsys)
    assert driver_run(repo, "once", capsys=capsys)[1].startswith("brief:")
    fork = [d for d in s.decisions() if d.kind == "fork"][0]
    main(["--root", str(repo), "decision", "answer", fork.id, "no"]); capsys.readouterr()
    (s.root / "cards" / "c-zzzz-agent.md").write_text("x\n", encoding="utf-8")
    head = git(repo, "rev-parse", "HEAD").strip()
    out = driver_run(repo, "once", capsys=capsys)[1]
    assert out.startswith("lock-lost: dirty tree:") and "c-zzzz-agent.md" in out
    assert git(repo, "rev-parse", "HEAD").strip() == head
    assert "Consumed:" not in s.load_decision(fork.id).body


# --- the project language (decision R3) ---

def test_driver_writes_prompt_in_project_language(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys, lang="ru")
    cid = add_card(repo, capsys, "Экспорт привычек в CSV")
    assert driver_run(repo, "once", capsys=capsys)[1].startswith("brief:")
    prompt = (s.root / "driver" / f"{cid}.brief.prompt.md").read_text(encoding="utf-8")
    assert "Вопрос:" in prompt and "Question:" not in prompt and "\n## Карточка\n" in prompt
    card = s.load_card(cid)
    assert card.status == "ready" and [x.title for x in card.steps] == ["Запись CSV", "Кнопка экспорта"]
    log = (s.root / "driver.log").read_text(encoding="utf-8")
    assert f"бриф {cid}: ready, шагов 2, развилок 0" in log


def test_driver_prompt_english_by_default(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    assert driver_run(repo, "once", capsys=capsys)[1].startswith("brief:")
    prompt = (s.root / "driver" / f"{cid}.brief.prompt.md").read_text(encoding="utf-8")
    assert "Question:" in prompt and "\n## Card\n" in prompt and not CYRILLIC.search(without_paths(prompt, tmp_path))


def test_env_lang_wins_over_manifest_for_the_prompt(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys, lang="ru")
    monkeypatch.setenv("NOD_LANG", "en")
    cid = add_card(repo, capsys)
    assert driver_run(repo, "once", capsys=capsys)[1].startswith("brief:")
    assert "Question:" in (s.root / "driver" / f"{cid}.brief.prompt.md").read_text(encoding="utf-8")


def test_driver_log_english_by_default(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys, brief="brief-forks-then-ok")
    cid = add_card(repo, capsys)
    full_cycle(repo, capsys, s, cid, fork_answer="no")
    log = (s.root / "driver.log").read_text(encoding="utf-8")
    assert log.count("\n") > 10 and not CYRILLIC.search(without_paths(log, tmp_path))
    answers = (s.root / "driver" / f"{cid}.answers.md").read_text(encoding="utf-8")
    assert answers.startswith("# Owner's answers on the card ") and "Answer: no." in answers
    pain = [d for d in s.decisions() if d.kind == "pain"][0]
    assert pain.question == "The backlog is empty. What hurts?"


def test_driver_log_follows_russian(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys, brief="brief-forks-then-ok", lang="ru")
    cid = add_card(repo, capsys, "Экспорт привычек в CSV")
    full_cycle(repo, capsys, s, cid, fork_answer="нет")
    log = (s.root / "driver.log").read_text(encoding="utf-8")
    assert f"бриф {cid}: команда запущена" in log and "приёмка" in log
    answers = (s.root / "driver" / f"{cid}.answers.md").read_text(encoding="utf-8")
    assert answers.startswith("# Ответы владельца по карточке ") and "Ответ: нет." in answers
    assert [d for d in s.decisions() if d.kind == "pain"][0].question == "Бэклог пуст. Что болит?"


@pytest.mark.parametrize("lang, question, reason", [
    ("en", "Log in to claude: run claude /login in a terminal. The claude answer: ",
     "the brief command waits for an owner action"),
    ("ru", "Войди в claude: в терминале выполни claude /login. Ответ claude: ",
     "команда brief ждёт действия владельца"),
])
def test_owner_action_text_follows_lang(repo, capsys, monkeypatch, tmp_path, lang, question, reason):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys, brief="brief-auth", lang=lang)
    cid = add_card(repo, capsys)
    assert driver_run(repo, "once", capsys=capsys)[1].startswith("brief:")
    d = [x for x in s.decisions() if x.kind == "owner-action"][0]
    assert d.question.startswith(question) and "OAuth" in d.question and d.reason == reason
    assert (d.proposed, d.options, d.card) == ("done", ["done", "postpone"], cid)


@pytest.mark.parametrize("lang, question", [("en", "Start the next batch? Cards: 1."),
                                            ("ru", "Запустить следующую пачку? Карточек: 1.")])
def test_next_batch_question_follows_lang(repo, capsys, monkeypatch, tmp_path, lang, question):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys, lang=lang)
    main(["--root", str(repo), "card", "add", "Weekly email digest", "--source", "import"]); capsys.readouterr()
    assert driver_run(repo, "once", capsys=capsys)[1].startswith("next-batch:")
    assert [d.question for d in s.decisions() if d.kind == "next-batch"] == [question]


@pytest.mark.parametrize("action", [("once",), ("--passes", "1")])
def test_dry_run_of_a_pass_is_refused(repo, capsys, monkeypatch, tmp_path, action):
    """`--dry-run` previews only `install` and `uninstall`: a pass with it would run the agent and spend money."""
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    code, out, err = driver_run(repo, *action, "--dry-run", capsys=capsys)
    assert code == 2 and out == ""
    assert "--dry-run" in err and "install" in err
    assert s.load_card(cid).status == "backlog" and not (s.root / "driver.log").exists()
