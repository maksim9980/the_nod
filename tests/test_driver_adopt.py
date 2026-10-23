"""A live pass: the agent output on disk, a brief without a commit and TOML, the rebrief in the prompt."""
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from the_nod import context, harness
from the_nod.cli import main
from the_nod.driver import apply_brief, files, log as dl, usage
from the_nod.model import Card
from the_nod.store import Store
from tests.conftest import git
from tests.driver_helpers import env_for_tests, fake, setup
from tests.fake_agent import FIXTURE, STEPS, TITLE, brief_text

EXACT_PAIR = re.compile(r"(?<!`)``(?!`)")  # empty backticks, not a code fence


def ctx_of(repo):
    return context.open(SimpleNamespace(root=str(repo)))


def go(repo, cid, mode):
    s = Store(repo / ".nod")
    h = harness.load(s)
    h = harness.Harness(h.adapter, h.driver_host, {**h.commands, "brief": fake(mode)})
    return apply_brief.brief(ctx_of(repo), h, dl.Log(s.root / "driver.log"), cid)


def add_card(repo, capsys) -> str:
    main(["--root", str(repo), "card", "add", TITLE])
    return capsys.readouterr().out.strip()


def log_text(s: Store) -> str:
    return (s.root / "driver.log").read_text(encoding="utf-8")


# --- item 1: the agent output ---

def test_output_files_and_log_line(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    assert go(repo, cid, "brief-ok") is True
    out = s.root / "driver" / f"{cid}.brief.out.txt"
    err = s.root / "driver" / f"{cid}.brief.err.txt"
    assert out.exists() and err.exists()
    assert f"output brief {cid}: code 0, " in log_text(s)


def test_output_keeps_claude_summary(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    assert go(repo, cid, "brief-auth") is False
    out = (s.root / "driver" / f"{cid}.brief.out.txt").read_text(encoding="utf-8")
    assert "OAuth" in out
    assert "is_error true" in log_text(s)


def test_claude_summary_fields():
    text = usage.claude_summary(FIXTURE.read_text(encoding="utf-8"))
    assert text == "subtype success, is_error false, terminal_reason completed, turns 4, $ 0.36"
    assert usage.claude_summary("not JSON") == ""


def test_output_tail_is_limited(tmp_path):
    store = Store(tmp_path / ".nod")
    store.root.mkdir(exist_ok=True)
    outcome = SimpleNamespace(stdout="я" * files.OUTPUT_LIMIT, stderr="")
    out, _ = files.save_output(store, "c-1", "brief", outcome)
    data = out.read_bytes()
    assert len(data) <= files.OUTPUT_LIMIT and data.decode("utf-8").startswith("я")


# --- item 2: the driver adopts the brief itself ---

def test_harness_knows_briefs_dir(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    assert harness.load(s).briefs_dir == "docs/briefs"


def test_brief_without_commit_and_toml_is_adopted(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    assert go(repo, cid, "brief-file-only") is True
    card = s.load_card(cid)
    rel = f"docs/briefs/{cid}.md"
    assert card.status == "ready" and card.brief == rel and [x.title for x in card.steps] == STEPS
    subjects = git(repo, "log", "-3", "--format=%s").splitlines()
    assert subjects[2] == f"docs(brief): {cid}" and subjects[0].startswith("state: ")
    assert git(repo, "status", "--porcelain", "--", "docs/briefs") == ""
    result = files.result_path(s, cid, "brief").read_text(encoding="utf-8")
    assert f'brief = "{rel}"' in result


def _last_attempt(repo, s, cid, *, out: bool) -> tuple[Path, float]:
    """A failed attempt with the command window moved into the past: the prompt at -60 s, the output at -30 s."""
    assert go(repo, cid, "brief-noresult") is False and "(1/2)" in log_text(s)
    now = time.time()
    prompt = files.prompt_path(s, cid, "brief")
    os.utime(prompt, (now - 60, now - 60))
    out_file = files.output_paths(s, cid, "brief")[0]
    if out:
        os.utime(out_file, (now - 30, now - 30))
    else:
        out_file.unlink()
    return prompt, now


def _brief_file(repo, name: str, mtime: float, title: str = TITLE) -> None:
    target = repo / "docs" / "briefs" / f"{name}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(brief_text(False, False).replace(f"# {TITLE}", f"# {title}", 1), encoding="utf-8")
    os.utime(target, (mtime, mtime))


def test_brief_of_last_attempt_adopted_without_command(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    prompt, now = _last_attempt(repo, s, cid, out=True)
    _brief_file(repo, cid, now - 45)
    assert go(repo, cid, "brief-fail") is True
    assert prompt.stat().st_mtime == pytest.approx(now - 60)
    assert f"adopted the brief of the last attempt: docs/briefs/{cid}.md" in log_text(s)
    assert s.load_card(cid).status == "ready"
    assert git(repo, "log", "-2", "--format=%s").splitlines()[1] == f"docs(brief): {cid}"


def test_brief_newer_than_last_output_not_adopted(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    _, now = _last_attempt(repo, s, cid, out=True)
    _brief_file(repo, "other", now - 10)
    assert go(repo, cid, "brief-noresult") is False
    assert s.load_card(cid).status == "returned" and "adopted the brief" not in log_text(s)


@pytest.mark.parametrize("title, adopted", [("Weekly email digest", False), ("  export habits  TO csv ", True)])
def test_without_output_only_same_title(repo, capsys, tmp_path, monkeypatch, title, adopted):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    _, now = _last_attempt(repo, s, cid, out=False)
    _brief_file(repo, "other", now - 10, title)
    assert go(repo, cid, "brief-noresult") is adopted
    assert ("adopted the brief of the last attempt: docs/briefs/other.md" in log_text(s)) is adopted
    assert s.load_card(cid).status == ("ready" if adopted else "returned")


def test_hand_written_result_adopted_without_command(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    _brief_file(repo, "hand", time.time())
    files.result_path(s, cid, "brief").write_text('brief = "docs/briefs/hand.md"\n', encoding="utf-8")
    assert go(repo, cid, "brief-fail") is True
    assert not Path(str(files.result_path(s, cid, "brief")) + ".prompt.txt").exists()
    assert not files.prompt_path(s, cid, "brief").exists()
    assert "adopted the result of the last attempt: docs/briefs/hand.md" in log_text(s)
    assert s.load_card(cid).brief == "docs/briefs/hand.md" and s.load_card(cid).status == "ready"
    assert git(repo, "log", "-2", "--format=%s").splitlines()[1] == "docs(brief): hand"


def test_result_with_uncommitted_brief_is_committed(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    assert go(repo, cid, "brief-nocommit") is True and s.load_card(cid).status == "ready"
    assert git(repo, "log", "-3", "--format=%s").splitlines()[2] == f"docs(brief): {cid}"
    assert git(repo, "status", "--porcelain", "--", "docs/briefs") == ""


def test_failed_command_reason_in_adoption_log(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    assert go(repo, cid, "brief-file-fail") is True
    assert f"adopted the brief docs/briefs/{cid}.md (command: the command exited with code 1" in log_text(s)


def test_protected_branch_fails_adoption(repo, capsys, tmp_path, monkeypatch):
    from the_nod.gitsync import GitSync, ProtectedBranch

    def refuse(self, paths, message):
        raise ProtectedBranch('branch "main" is protected')

    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    monkeypatch.setattr(GitSync, "commit_paths", refuse)
    assert go(repo, cid, "brief-file-only") is False
    assert 'is not committed: branch "main" is protected' in log_text(s) and "(1/2)" in log_text(s)


def test_old_brief_not_adopted_before_command(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    target = repo / "docs" / "briefs" / "old.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(brief_text(False, False), encoding="utf-8")
    old = time.time() - 60
    os.utime(target, (old, old))
    assert go(repo, cid, "brief-noresult") is False
    assert go(repo, cid, "brief-noresult") is False
    assert s.load_card(cid).status == "returned" and "adopted the brief" not in log_text(s)


# --- item 4: the rebrief lines only with a non-empty `{brief}` ---

def _values(brief: str) -> dict[str, str]:
    return {**{name: f"<{name}>" for name in harness.PLACEHOLDERS}, "brief": brief}


@pytest.mark.parametrize("adapter", harness.ADAPTERS)
def test_rebrief_lines_only_with_brief(adapter):
    card = Card(id="c-1", title=TITLE, status="briefing", created="2026-10-21", source="owner")
    empty = files.prompt_text(adapter, "brief", _values(""), card)
    assert "repeat brief" not in empty and not EXACT_PAIR.search(empty)
    again = files.prompt_text(adapter, "brief", _values("docs/briefs/x.md"), card)
    assert "repeat brief" in again and "`docs/briefs/x.md`" in again


def test_first_brief_prompt_has_no_empty_backticks(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    s = setup(repo, capsys)
    cid = add_card(repo, capsys)
    go(repo, cid, "brief-ok")
    text = Path(files.prompt_path(s, cid, "brief")).read_text(encoding="utf-8")
    assert "repeat brief" not in text and not EXACT_PAIR.search(text)
