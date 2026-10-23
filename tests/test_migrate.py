"""`nod migrate`: an older `.sprintboot/` state becomes `.nod/` with the canonical values."""
import json
import re
import subprocess
from pathlib import Path

import pytest

from the_nod import frontmatter, harness, i18n, migrate, model as m
from the_nod.cli import main
from the_nod.driver import plan
from the_nod.mcp.tools import TOOLS, build
from the_nod.store import Store
from tests.conftest import BRANCH, git

OLD = migrate.LEGACY_DIR
SUBJECT = "state: migrate .sprintboot to .nod"
CYRILLIC = re.compile(r"[Ѐ-ӿ]")

MANIFEST = """\
# Manifest of the older version: sb doctor checks it.
adapter = "tidepool-legacy"
driver_host = "laptop"
[commands]
brief = ""
run = "sb run {card} --step {step}"
accept = ""

[needs]
python = "3.13"
sb = "sb"
"""
RUN_LINE = 7  # the line of `run = "sb run ..."` after the migration: `lang = "ru"` goes in at line 2
NEEDS_LINE = len(MANIFEST.splitlines()) + 1  # `nod = "sb"` after the migration
GITIGNORE = """\
__pycache__/
.sprintboot/state.json
.sprintboot/seen.toml
.sprintboot/driver.log
.sprintboot/driver.log.1
.sprintboot/driver/
dist/
"""
REVIEW_BODY = """\
# Обзор недели 2026-42

## Что улучшить

1. [предлагается] Shorter briefs for small cards
2. [внесено] Run the habit grid tests before each step

## По карточкам

нет
"""


def _strings(items: list[str]) -> str:
    return "[" + ", ".join(f'"{item}"' for item in items) + "]"


def old_card(id: str, title: str, status: str) -> str:
    return (f'+++\nid = "{id}"\ntitle = "{title}"\nstatus = "{status}"\ncreated = "2026-10-12T09:00:00"\n'
            f'source = "owner"\nsteps = []\n+++\n')


def old_decision(id: str, kind: str, question: str, proposed: str, options: list[str], *,
                 card: str | None = None, answer: str | None = None, body: str = "") -> str:
    """A decision file as the older version wrote it."""
    lines = ["+++", f'id = "{id}"', f'kind = "{kind}"', 'created = "2026-10-19T09:00:00"',
             f'question = "{question}"', f'proposed = "{proposed}"', f"options = {_strings(options)}", 'reason = ""']
    if card:
        lines.append(f'card = "{card}"')
    if answer is not None:
        lines += [f'answer = "{answer}"', 'answered_at = "2026-10-19T10:00:00"', 'answered_by = "owner"']
    lines += ['note = ""', "+++"]
    return "\n".join(lines) + "\n" + body


FILES = {
    "harness.toml": MANIFEST,
    "order.md": "# Порядок бэклога\n\nc-a002  Weekly email digest\n",
    "cards/c-a001-export-habits-to-csv.md": old_card("c-a001", "Export habits to CSV", "returned"),
    "cards/c-a002-weekly-email-digest.md": old_card("c-a002", "Weekly email digest", "backlog"),
    "cards/c-a003-dark-mode-for-the-habit-grid.md": old_card("c-a003", "Dark mode for the habit grid", "done"),
    "decisions/d-a001-log-in-to-the-mail-service.md": old_decision(
        "d-a001", "owner-action", "Log in to the mail service", "сделано", ["сделано", "отложить"],
        card="c-a002", answer="отложить", body="Учтено: 2026-10-19T10:05:00"),
    "decisions/d-a002-take-the-next-batch.md": old_decision(
        "d-a002", "next-batch", "Take the next batch?", "да", ["да", "нет"], answer="да",
        body="- c-a002  Weekly email digest\nУчтено: 2026-10-19T10:06:00"),
    "decisions/d-a003-what-hurts-now.md": old_decision(
        "d-a003", "pain", "What hurts now?", "подождать", ["подождать"]),
    "decisions/d-a004-what-hurts-this-week.md": old_decision(
        "d-a004", "pain", "What hurts this week?", "подождать", ["подождать"],
        answer="Streaks reset at midnight UTC", body="Карточка: c-a003"),
    "decisions/d-a005-grid-colours.md": old_decision(
        "d-a005", "fork", "Grid colours?", "да, как в макете", ["да, как в макете", "да", "нет"],
        card="c-a003", answer="да"),
    "decisions/d-a006-return-export-habits-to-csv.md": old_decision(
        "d-a006", "return", "Return: Export habits to CSV", "rerun", ["rerun", "backlog"],
        card="c-a001", answer="rerun", body="Учтено: 2026-10-19T10:07:00"),
    "decisions/d-a007-csv-columns.md": old_decision(
        "d-a007", "fork", "CSV columns?", "дата и привычка", ["дата и привычка", "нет"],
        card="c-a001", answer="нет", body="Учтено: 2026-10-19T10:08:00"),
    "acceptance/c-a003/index.md": (
        '+++\ncard = "c-a003"\nlevel = 1\nresult = "не проверено"\ncreated = "2026-10-19T11:00:00"\n'
        'evidence = ""\nframes = []\nsteps = []\nreport = ".sprintboot/driver/c-a003.step1.report.md"\n+++\n'),
    "reviews/2026-42.md": (
        '+++\nweek = "2026-42"\nsince = "2026-10-12T09:00:00"\nuntil = "2026-10-19T09:00:00"\n'
        'generated_at = "2026-10-19T09:00:00"\nsuggestions = [\n'
        '  { n = 1, rule = "brief-size", target = "prompts", text = "Shorter briefs for small cards",'
        ' status = "предлагается" },\n'
        '  { n = 2, rule = "tests-first", target = "commands", text = "Run the habit grid tests before each step",'
        ' status = "внесено" },\n]\n+++\n' + REVIEW_BODY),
}
LOCAL = {"state.json": '{"schema": 1}\n', "seen.toml": 'laptop = "2026-10-19T09:00:00"\n',
         "driver/c-a003.step1.report.md": "Report of the step.\n"}


KEPT_MANIFEST = 'lang = "en"\nadapter = "default"\n[git]\npush = false\n'


def write_legacy(root: Path) -> None:
    """The older state of Tidepool in `root`: committed files plus the local ones."""
    for rel, text in {**FILES, **LOCAL}.items():
        path = root / OLD / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def legacy(repo: Path) -> Path:
    """The repo with the older state committed and pushed, the .gitignore of the older version."""
    (repo / ".gitignore").write_text(GITIGNORE, encoding="utf-8", newline="\n")
    write_legacy(repo)
    git(repo, "add", ".gitignore", OLD)
    git(repo, "commit", "-q", "-m", "state: older version")
    git(repo, "push", "-q", "origin", BRANCH)
    return repo


def run(root: Path, *args: str, capsys) -> tuple[int, str, str]:
    code = main(["--root", str(root), *args])
    out = capsys.readouterr()
    return code, out.out, out.err


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def status_lines(repo: Path) -> str:
    return git(repo, "status", "--porcelain", "--ignored", "-uall")


def tree_bytes(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def meta(path: Path) -> tuple[dict, str]:
    return frontmatter.parse(path.read_text(encoding="utf-8"))


def decision(repo: Path, id: str) -> tuple[dict, str]:
    [path] = (repo / ".nod" / "decisions").glob(f"{id}-*.md")
    return meta(path)


# --- the hint ---

def test_legacy_state_hint(legacy, capsys, monkeypatch):
    code, out, err = run(legacy, "status", capsys=capsys)
    assert code == 2 and out == ""
    assert err.strip() == "error: found .sprintboot/ from an older version: run nod migrate"
    monkeypatch.chdir(legacy / OLD / "cards")
    assert main(["status"]) == 2
    assert "nod migrate" in capsys.readouterr().err
    monkeypatch.setenv(i18n.ENV, "ru")
    assert main(["--root", str(legacy), "status"]) == 2
    assert capsys.readouterr().err.strip() == "ошибка: найдена .sprintboot/ от старой версии: запусти nod migrate"


def test_legacy_hint_outside_git(tmp_path, capsys, monkeypatch):
    write_legacy(tmp_path)
    deep = tmp_path / "src" / "habits"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    assert main(["status"]) == 2
    assert "run nod migrate" in capsys.readouterr().err


def test_no_hint_without_the_older_folder(repo, capsys):
    code, _, err = run(repo, "status", capsys=capsys)
    assert code == 2 and err.strip() == "error: no state: run nod init"


# --- dry run ---

def test_dry_run_changes_nothing(legacy, capsys):
    before, files, sha = status_lines(legacy), tree_bytes(legacy / OLD), head(legacy)
    code, out, err = run(legacy, "migrate", "--dry-run", capsys=capsys)
    assert code == 0, err
    assert out.startswith("dry run, nothing changed: nod migrate would")
    assert "decisions/d-a001-log-in-to-the-mail-service.md" in out and SUBJECT in out
    assert "decisions/d-a005-grid-colours.md" not in out  # a fork stays as it is
    assert "  pull --ff-only from origin first" in out.splitlines()  # planned, not done
    assert 'adapter "tidepool-legacy"' in err and f"harness.toml:{RUN_LINE}:" in err
    assert status_lines(legacy) == before and head(legacy) == sha
    assert tree_bytes(legacy / OLD) == files and not (legacy / ".nod").exists()
    assert (legacy / ".gitignore").read_text(encoding="utf-8") == GITIGNORE


def test_dry_run_json(legacy, capsys):
    code, out, _ = run(legacy, "migrate", "--dry-run", "--json", capsys=capsys)
    data = json.loads(out)
    assert code == 0 and data["dry_run"] is True and data["commit"] is None
    assert data["from"] == OLD and data["to"] == ".nod" and data["push"] is True
    assert sorted(data["rewritten"]) == sorted([
        "acceptance/c-a003/index.md", "decisions/d-a001-log-in-to-the-mail-service.md",
        "decisions/d-a002-take-the-next-batch.md", "decisions/d-a003-what-hurts-now.md",
        "decisions/d-a004-what-hurts-this-week.md", "decisions/d-a006-return-export-habits-to-csv.md",
        "decisions/d-a007-csv-columns.md", "reviews/2026-42.md"])
    assert data["manifest"] == {"adapter": "tidepool-legacy", "needs_renamed": True, "lang_added": True,
                                "git_added": True}
    assert data["local"] is None and data["pulled"] is False
    assert data["gitignore_lines"] == 5 and len(data["warnings"]) == 3


def test_dry_run_in_russian(legacy, capsys, monkeypatch):
    monkeypatch.setenv(i18n.ENV, "ru")
    code, out, err = run(legacy, "migrate", "--dry-run", capsys=capsys)
    assert code == 0 and out.startswith("пробный прогон, ничего не изменено")
    assert "адаптера «tidepool-legacy»" in err


# --- the migration ---

def test_migrate_renames_and_rewrites(legacy, capsys):
    code, out, err = run(legacy, "migrate", capsys=capsys)
    assert code == 0, err
    nod = legacy / ".nod"
    assert nod.is_dir() and not (legacy / OLD).exists()
    owner, body = decision(legacy, "d-a001")
    assert (owner["answer"], owner["proposed"], owner["options"]) == ("postpone", "done", ["done", "postpone"])
    assert body == "Consumed: 2026-10-19T10:05:00"
    batch, body = decision(legacy, "d-a002")
    assert (batch["answer"], batch["options"]) == ("yes", ["yes", "no"])
    assert body.splitlines() == ["- c-a002  Weekly email digest", "Consumed: 2026-10-19T10:06:00"]
    pain, _ = decision(legacy, "d-a003")
    assert (pain["proposed"], pain["options"], "answer" in pain) == ("wait", ["wait"], False)
    told, body = decision(legacy, "d-a004")
    assert told["answer"] == "Streaks reset at midnight UTC" and body == "Card: c-a003"
    fork, _ = decision(legacy, "d-a005")
    assert (fork["proposed"], fork["options"], fork["answer"]) == ("да, как в макете", ["да, как в макете", "да", "нет"], "да")
    accepted, _ = meta(nod / "acceptance" / "c-a003" / "index.md")
    assert accepted["result"] == "unverified" and accepted["report"] == ".nod/driver/c-a003.step1.report.md"
    review, body = meta(nod / "reviews" / "2026-42.md")
    assert [s["status"] for s in review["suggestions"]] == ["proposed", "applied"]
    assert "1. [proposed] Shorter briefs" in body and "2. [applied] Run the habit grid" in body
    assert "## Что улучшить" in body and not re.search(r"предлагается|внесено", body)
    # Untouched files keep their bytes; the local files moved along.
    for rel in ("order.md", "cards/c-a001-export-habits-to-csv.md", "decisions/d-a005-grid-colours.md"):
        assert (nod / rel).read_text(encoding="utf-8") == FILES[rel]
    assert (nod / "seen.toml").read_text(encoding="utf-8") == LOCAL["seen.toml"]
    assert (nod / "driver" / "c-a003.step1.report.md").is_file()
    store = Store(nod)
    assert len(store.decisions()) == 7 and store.load_acceptance("c-a003").result == "unverified"
    assert out.splitlines()[:2] == ["pulled from origin first", "moved .sprintboot/ to .nod/"]


def test_old_consumed_decisions_do_not_react(legacy, capsys):
    assert run(legacy, "migrate", capsys=capsys)[0] == 0
    store = Store(legacy / ".nod")
    assert plan.reactions(store.cards(), store.decisions()) == []
    # Without the rewrite the old marker reads as "not consumed": the answered return would react again.
    returned = m.Card(id="c-a001", title="Export habits to CSV", status="returned", created="2026-10-12T09:00:00",
                      source="owner")
    old = m.Decision(id="d-a006", kind="return", created="2026-10-19T09:00:00", question="Return", proposed="rerun",
                     options=["rerun", "backlog"], card="c-a001", answer="rerun", body="Учтено: 2026-10-19T10:07:00")
    assert plan.reactions([returned], [old]) == [plan.Action("react", card="c-a001", decision="d-a006")]


def test_migrate_single_commit(legacy, capsys):
    before = head(legacy)
    code, out, err = run(legacy, "migrate", capsys=capsys)
    assert code == 0, err
    assert git(legacy, "log", "--format=%s", f"{before}..HEAD").splitlines() == [SUBJECT]
    changed = git(legacy, "-c", "core.quotePath=false", "show", "--name-status", "--format=", "--no-renames",
                  "HEAD").splitlines()
    committed = sorted(FILES)
    assert sorted(changed) == sorted(["M\t.gitignore", *(f"D\t{OLD}/{rel}" for rel in committed),
                                      *(f"A\t.nod/{rel}" for rel in committed)])
    assert git(legacy, "ls-files", "--", OLD) == ""
    assert git(legacy, "ls-files", "--", ".nod/state.json", ".nod/seen.toml", ".nod/driver") == ""
    assert git(legacy, "status", "--porcelain") == ""
    assert f"commit {head(legacy)[:7]}: {SUBJECT}" in out
    # `[git] push = true` came with the migration: the commit reached origin.
    remote = git(legacy.parent / "remote.git", "rev-parse", BRANCH).strip()
    assert remote == head(legacy)


def test_migrate_manifest(legacy, capsys):
    code, out, err = run(legacy, "migrate", capsys=capsys)
    assert code == 0
    text = (legacy / ".nod" / "harness.toml").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[:3] == ["# Manifest of the older version: sb doctor checks it.", 'lang = "ru"', 'adapter = "default"']
    assert lines[RUN_LINE - 1] == 'run = "sb run {card} --step {step}"'
    assert 'nod = "sb"' in lines and 'sb = "sb"' not in lines
    assert text.endswith("\n[git]\npush = true\n")
    loaded = harness.load(Store(legacy / ".nod"))
    assert loaded.adapter == "default" and loaded.push is True and loaded.needs.nod == "sb" and loaded.lang == "ru"
    warnings = err.splitlines()
    assert 'harness.toml: adapter "tidepool-legacy" is not in this version: set to "default"' in warnings
    assert f'harness.toml:{RUN_LINE}: names the older version, check it: run = "sb run {{card}} --step {{step}}"' in warnings
    assert f"harness.toml:{NEEDS_LINE}:" in err  # the [needs] value is a command of the older version
    assert 'harness.toml: lang = "ru" added, the older version spoke Russian; set lang = "en" for English' in out
    assert not [line for line in warnings if line.startswith("harness.toml:1:")]  # comments are not checked


def test_migrate_keeps_a_git_table(legacy, capsys):
    """A manifest that already has `lang` and `[git]` keeps them: without push the migration stays local."""
    path = legacy / OLD / "harness.toml"
    path.write_text(KEPT_MANIFEST, encoding="utf-8", newline="\n")
    git(legacy, "commit", "-q", "-am", "state: local only")
    remote = git(legacy.parent / "remote.git", "rev-parse", BRANCH).strip()
    code, out, err = run(legacy, "migrate", capsys=capsys)
    assert code == 0 and err == ""
    assert (legacy / ".nod" / "harness.toml").read_text(encoding="utf-8") == KEPT_MANIFEST
    assert "lang" not in out and "pull" not in out
    assert git(legacy.parent / "remote.git", "rev-parse", BRANCH).strip() == remote != head(legacy)


def test_migrate_gitignore(legacy, capsys):
    assert run(legacy, "migrate", capsys=capsys)[0] == 0
    assert (legacy / ".gitignore").read_text(encoding="utf-8") == GITIGNORE.replace(".sprintboot/", ".nod/")
    assert "!! .nod/state.json" in status_lines(legacy)


def test_status_works_after_migrate(legacy, capsys):
    assert run(legacy, "migrate", capsys=capsys)[0] == 0
    code, out, err = run(legacy, "status", "--json", capsys=capsys)
    assert code == 0, err
    state = json.loads(out)
    assert [(d["id"], d["proposed"], d["options"]) for d in state["waiting"]] == [("d-a003", "wait", ["wait"])]
    code, _, err = run(legacy, "review", "mark", "2026-42", "1", "--applied", capsys=capsys)
    assert code == 0, err
    _, body = meta(legacy / ".nod" / "reviews" / "2026-42.md")
    assert "1. [applied] Shorter briefs" in body


def test_migrate_writes_a_fresh_snapshot(legacy, capsys):
    assert run(legacy, "migrate", capsys=capsys)[0] == 0
    state = json.loads((legacy / ".nod" / "state.json").read_text(encoding="utf-8"))
    assert [d["id"] for d in state["waiting"]] == ["d-a003"]


def test_migrate_output_has_no_cyrillic_in_english(legacy, capsys):
    code, out, err = run(legacy, "migrate", capsys=capsys)
    assert code == 0 and not CYRILLIC.search(out + err)


# --- refusals ---

def test_migrate_refuses_twice_and_on_main(legacy, tmp_path, capsys):
    assert run(legacy, "migrate", capsys=capsys)[0] == 0
    sha = head(legacy)
    code, out, err = run(legacy, "migrate", capsys=capsys)
    assert code == 2 and out == "" and err.strip() == "error: .nod/ already exists: nothing to migrate into"
    assert head(legacy) == sha
    other = tmp_path / "on-main"
    other.mkdir()
    git(other, "init", "-q", "-b", "main")
    git(other, "config", "user.name", "Test")
    git(other, "config", "user.email", "test@example.com")
    write_legacy(other)
    git(other, "add", OLD)
    git(other, "commit", "-q", "-m", "state: older version")
    files, sha = tree_bytes(other / OLD), head(other)
    code, out, err = run(other, "migrate", capsys=capsys)
    assert code == 3 and out == "" and 'branch "main" is protected' in err
    assert tree_bytes(other / OLD) == files and not (other / ".nod").exists() and head(other) == sha


def test_migrate_refuses_without_the_older_folder(repo, capsys):
    code, _, err = run(repo, "migrate", capsys=capsys)
    assert code == 2 and "nothing to migrate" in err and not (repo / ".nod").exists()


def test_migrate_refuses_dirty_files(legacy, capsys):
    path = legacy / OLD / "decisions" / "d-a003-what-hurts-now.md"
    path.write_text(path.read_text(encoding="utf-8") + "edited\n", encoding="utf-8")
    (legacy / OLD / "cards" / "c-a009-new.md").write_text(old_card("c-a009", "New", "backlog"), encoding="utf-8")
    (legacy / OLD / "state.json").write_text("{}\n", encoding="utf-8")  # a local file is not dirt
    code, _, err = run(legacy, "migrate", capsys=capsys)
    assert code == 2 and "uncommitted changes" in err
    assert "d-a003-what-hurts-now.md" in err and "c-a009-new.md" in err and "state.json" not in err
    assert not (legacy / ".nod").exists()


def test_migrate_refuses_a_dirty_gitignore(legacy, capsys):
    (legacy / ".gitignore").write_text(GITIGNORE + "build/\n", encoding="utf-8", newline="\n")
    code, _, err = run(legacy, "migrate", capsys=capsys)
    assert code == 2 and ".gitignore" in err and not (legacy / ".nod").exists()


def test_migrate_refuses_a_state_that_would_not_read(legacy, capsys):
    path = legacy / OLD / "acceptance" / "c-a003" / "index.md"
    path.write_text(FILES["acceptance/c-a003/index.md"].replace("не проверено", "почти"), encoding="utf-8")
    git(legacy, "commit", "-q", "-am", "state: odd value")
    code, _, err = run(legacy, "migrate", capsys=capsys)
    assert code == 2 and "index.md" in err and "result" in err
    assert (legacy / OLD).is_dir() and not (legacy / ".nod").exists()


def test_migrate_refused_to_the_agent(legacy, capsys, monkeypatch):
    monkeypatch.setenv("NOD_AGENT", "1")
    code, _, err = run(legacy, "migrate", capsys=capsys)
    assert code == 2 and "not available to the driver's agent" in err and (legacy / OLD).is_dir()


def test_migrate_is_not_an_mcp_tool():
    for tools in (TOOLS, build("ru")):
        assert not [tool.name for tool in tools if "migrate" in tool.name]
        # `argv` is `partial(_build, lang, prefix, ...)`: no tool builds a `migrate` command line.
        assert not [tool.name for tool in tools if tool.argv.args[1][:1] == ("migrate",)]


# --- outside git and from a run's worktree ---

def test_migrate_outside_git(tmp_path, capsys):
    write_legacy(tmp_path)
    code, out, err = run(tmp_path, "migrate", capsys=capsys)
    assert code == 0, err
    assert (tmp_path / ".nod" / "decisions").is_dir() and not (tmp_path / OLD).exists()
    assert "commit" not in out
    assert Store(tmp_path / ".nod").load_acceptance("c-a003").result == "unverified"


def test_migrate_from_a_worktree_moves_the_main_tree(legacy, capsys):
    other = legacy.parent / "wt"
    git(legacy, "worktree", "add", "-q", str(other), "-b", f"{BRANCH}-run-1")
    code, _, err = run(other, "migrate", capsys=capsys)
    assert code == 0, err
    assert (legacy / ".nod").is_dir() and not (legacy / OLD).exists()
    assert git(legacy, "log", "-1", "--format=%s") == SUBJECT + "\n"


# --- a failure after the move is undone ---

def failing_hook(repo: Path) -> Path:
    """A pre-commit hook that refuses every commit."""
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\necho the hook refuses >&2\nexit 1\n", encoding="utf-8", newline="\n")
    hook.chmod(0o755)  # git skips a hook without the executable bit on POSIX
    git(repo, "config", "core.hooksPath", ".git/hooks")
    return hook


def assert_untouched(repo: Path, files: dict[str, bytes], sha: str) -> None:
    """The repo as before `nod migrate`: the older folder byte for byte, nothing staged, no commit."""
    assert tree_bytes(repo / OLD) == files and not (repo / ".nod").exists()
    assert (repo / ".gitignore").read_text(encoding="utf-8") == GITIGNORE
    assert head(repo) == sha and git(repo, "status", "--porcelain") == ""
    assert git(repo, "diff", "--cached", "--name-only") == ""


def test_failing_commit_hook_undoes_the_move(legacy, capsys):
    files, sha = tree_bytes(legacy / OLD), head(legacy)
    hook = failing_hook(legacy)
    code, _, err = run(legacy, "migrate", capsys=capsys)
    assert code == 2 and "error: the migration was undone, nothing changed: git commit:" in err
    assert "the hook refuses" in err
    assert_untouched(legacy, files, sha)
    hook.unlink()
    assert run(legacy, "migrate", capsys=capsys)[0] == 0
    assert git(legacy, "log", "-1", "--format=%s").strip() == SUBJECT


def test_failing_rewrite_undoes_the_move(legacy, capsys, monkeypatch):
    files, sha = tree_bytes(legacy / OLD), head(legacy)
    real, calls = migrate.write_text_atomic, []

    def flaky(path, text):
        calls.append(path)
        if len(calls) == 3:
            raise OSError(28, "No space left on device", str(path))
        real(path, text)

    monkeypatch.setattr(migrate, "write_text_atomic", flaky)
    code, _, err = run(legacy, "migrate", capsys=capsys)
    assert code == 2 and "the migration was undone, nothing changed" in err and "No space left on device" in err
    assert len(calls) == 3
    assert_untouched(legacy, files, sha)


# --- a second machine and origin ---

def clone(repo: Path, name: str) -> Path:
    """Another machine: a clone of origin on the work branch."""
    path = repo.parent / name
    git(repo.parent, "clone", "-q", "-b", BRANCH, str(repo.parent / "remote.git"), str(path))
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.com")
    return path


def origin_sha(repo: Path) -> str:
    return git(repo.parent / "remote.git", "rev-parse", BRANCH).strip()


def push_a_card(machine: Path) -> str:
    """A state commit of the older version on `machine`, pushed; its sha."""
    path = machine / OLD / "cards" / "c-a004-habit-reminders.md"
    path.write_text(old_card("c-a004", "Habit reminders", "backlog"), encoding="utf-8", newline="\n")
    git(machine, "add", OLD)
    git(machine, "commit", "-q", "-m", "state: card add c-a004")
    git(machine, "push", "-q", "origin", BRANCH)
    return head(machine)


def test_second_machine_moves_its_local_files(legacy, capsys):
    desktop = clone(legacy, "desktop")
    own = {"seen.toml": 'desktop = "2026-10-18T08:00:00"\n', "driver.log": "older log\n",
           "driver/c-a003.answers.md": "answers\n", "state.json": "{}\n"}
    for rel, text in own.items():
        path = desktop / OLD / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    assert run(legacy, "migrate", capsys=capsys)[0] == 0  # the laptop migrates and pushes
    git(desktop, "pull", "-q", "--ff-only")
    assert (desktop / ".nod" / "decisions").is_dir() and sorted(tree_bytes(desktop / OLD)) == sorted(own)
    code, _, err = run(desktop, "status", capsys=capsys)  # no hint once .nod/ is there
    assert code == 0 and "nod migrate" not in err
    (desktop / ".nod" / "driver.log").write_text("newer log\n", encoding="utf-8")
    sha = head(desktop)
    code, out, err = run(desktop, "migrate", capsys=capsys)
    assert code == 0, err
    assert "local files of this machine moved from .sprintboot/ to .nod/: 3" in out
    assert "seen.toml: merged with the one in .nod/" in out and "state.json: the older snapshot" in out
    assert out.splitlines()[-1] == "nothing to commit: local files stay out of git"
    assert "driver.log: stays in .sprintboot/, .nod/ has its own" in err
    nod = desktop / ".nod"
    assert (nod / "driver" / "c-a003.answers.md").read_text(encoding="utf-8") == "answers\n"
    assert (nod / "driver.log").read_text(encoding="utf-8") == "newer log\n"
    seen = (nod / "seen.toml").read_text(encoding="utf-8")
    assert 'desktop = "2026-10-18T08:00:00"' in seen and len(seen.splitlines()) == 2
    assert tree_bytes(desktop / OLD) == {"driver.log": b"older log\n"}
    assert head(desktop) == sha and git(desktop, "status", "--porcelain", "-uall") == f"?? {OLD}/driver.log\n"


def test_both_folders_with_state_files_are_refused(legacy, capsys):
    assert run(legacy, "migrate", capsys=capsys)[0] == 0
    (legacy / OLD / "cards").mkdir(parents=True)
    (legacy / OLD / "cards" / "c-a009-new.md").write_text(old_card("c-a009", "New", "backlog"), encoding="utf-8")
    code, _, err = run(legacy, "migrate", capsys=capsys)
    assert code == 2 and "still holds state files" in err and "c-a009-new.md" in err


def test_migrate_pulls_first_when_behind(legacy, capsys):
    pushed = push_a_card(clone(legacy, "desktop"))
    code, out, err = run(legacy, "migrate", capsys=capsys)
    assert code == 0, err
    assert out.splitlines()[0] == "pulled from origin first"
    assert (legacy / ".nod" / "cards" / "c-a004-habit-reminders.md").is_file()
    assert git(legacy, "rev-parse", "HEAD~1").strip() == pushed and origin_sha(legacy) == head(legacy)


def test_migrate_refuses_when_diverged(legacy, capsys):
    push_a_card(clone(legacy, "desktop"))
    (legacy / "README.md").write_text("# Tidepool\n", encoding="utf-8")
    git(legacy, "commit", "-q", "-am", "docs: title")
    files, sha = tree_bytes(legacy / OLD), head(legacy)
    code, out, err = run(legacy, "migrate", capsys=capsys)
    assert code == 3 and out == ""
    assert "error: could not bring the branch up to date with origin, nothing moved:" in err
    assert tree_bytes(legacy / OLD) == files and not (legacy / ".nod").exists() and head(legacy) == sha


def test_dry_run_plans_the_pull_without_it(legacy, capsys):
    push_a_card(clone(legacy, "desktop"))
    sha = head(legacy)
    code, out, _ = run(legacy, "migrate", "--dry-run", capsys=capsys)
    assert code == 0 and "  pull --ff-only from origin first" in out.splitlines()
    assert head(legacy) == sha and not (legacy / OLD / "cards" / "c-a004-habit-reminders.md").exists()


# --- forks, the manifest, init ---

def test_fork_with_a_consumed_marker_is_converted(legacy, capsys):
    assert run(legacy, "migrate", capsys=capsys)[0] == 0
    fork, body = decision(legacy, "d-a007")
    assert (fork["proposed"], fork["options"], fork["answer"]) == ("дата и привычка", ["дата и привычка", "нет"], "нет")
    assert body == "Consumed: 2026-10-19T10:08:00"


def commit_manifest(repo: Path, text: str) -> None:
    (repo / OLD / "harness.toml").write_text(text, encoding="utf-8", newline="\n")
    git(repo, "commit", "-q", "-am", "state: manifest")


def test_inline_needs_table_is_renamed(legacy, capsys):
    commit_manifest(legacy, 'adapter = "default"\nneeds = { python = "3.13", sb = "" }\n')
    code, out, err = run(legacy, "migrate", capsys=capsys)
    assert code == 0, err
    assert "harness.toml: [needs] sb becomes nod" in out
    loaded = harness.load(Store(legacy / ".nod"))
    assert loaded.needs.nod == "" and loaded.lang == "ru" and loaded.push is True


def test_manifest_that_would_not_pass_is_refused(legacy, capsys):
    commit_manifest(legacy, 'adapter = "default"\n[commands]\nrun = "sb run {title}"\n')
    files, sha = tree_bytes(legacy / OLD), head(legacy)
    code, out, err = run(legacy, "migrate", "--dry-run", capsys=capsys)
    assert code == 2 and out == "" and "harness.toml would not pass the check after the migration" in err
    assert "title" in err
    assert_untouched(legacy, files, sha)


def test_init_refuses_next_to_the_older_folder(legacy, capsys, monkeypatch):
    code, out, err = run(legacy, "init", capsys=capsys)
    assert code == 2 and out == ""
    assert err.strip() == "error: found .sprintboot/ from an older version: run nod migrate"
    monkeypatch.setenv(i18n.ENV, "ru")
    code, _, err = run(legacy, "init", capsys=capsys)
    assert code == 2 and err.strip() == "ошибка: найдена .sprintboot/ от старой версии: запусти nod migrate"
    assert not (legacy / ".nod").exists() and (legacy / ".gitignore").read_text(encoding="utf-8") == GITIGNORE
