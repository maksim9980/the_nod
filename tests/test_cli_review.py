import json
import re

from the_nod import gitsync, model as m
from the_nod.cli import main
from the_nod.store import Store
from tests.conftest import enable_push, git

CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def seed(root):
    """A small Tidepool state with English texts only: a running card, a backlog card, a done card with one run."""
    s = Store(root / ".nod")
    s.save_card(m.Card(id="c-aaaa", title="Export habits to CSV", status="running", created="2026-10-10T00:00:00",
                       source="owner", steps=[m.Step(1, "Step 1", True), m.Step(2, "Step 2")]))
    s.save_card(m.Card(id="c-bbbb", title="Weekly email digest", status="backlog", created="2026-10-10T00:00:00",
                       source="owner"))
    s.save_card(m.Card(id="c-cccc", title="Dark mode for the habit grid", status="done", created="2026-10-10T00:00:00",
                       source="owner", closed_at="2026-10-19T12:00:00", closed_by="owner"))
    s.save_decision(m.Decision(id="d-1111", kind="verdict", card="c-cccc", created="2026-10-19T11:00:00",
                               question="Accept the verdict: Dark mode", proposed="accept",
                               options=["accept", "return"]))
    s.save_run(m.Run(id="r-1111", card="c-aaaa", step=2, started="2026-10-20T09:00:00", contracts_total=5,
                     contracts_done=2))
    s.save_run(m.Run(id="r-0000", card="c-cccc", step=1, started="2026-10-18T09:00:00",
                     finished="2026-10-18T10:00:00", result="ok", tokens=3800000))
    s.set_order(["c-bbbb", "c-aaaa"])
    return s


def commit_seed(repo):
    s = seed(repo)
    git(repo, "add", ".nod")
    git(repo, "commit", "-m", "state: seed")
    return s


def set_lang(repo, value: str) -> None:
    path = repo / ".nod" / "harness.toml"
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r'(?m)^lang = ".*"$', f'lang = "{value}"', text), encoding="utf-8")


def test_review_week_writes_file_commits_and_snapshot(repo, capsys):
    commit_seed(repo)
    assert main(["--root", str(repo), "--json", "review", "week", "--since", "2026-10-14T00:00:00"]) == 0
    out = json.loads(capsys.readouterr().out)
    week = out["week"]; assert re.fullmatch(r"\d{4}-\d{2}", week) and out["path"] == f"reviews/{week}.md"
    # The unfinished run r-1111 from the seed is in the period too (by `started`), hence 2.
    assert out["runs"] == 2 and out["tokens"] == 3800000 and out["commits"] >= 1
    text = (repo / ".nod" / out["path"]).read_text(encoding="utf-8")
    assert text.startswith("+++\n") and "## What to improve" in text and "## By agent command" in text
    assert f"state: review week {week}" in git(repo, "log", "--format=%s", "-3")
    state = json.loads((repo / ".nod" / "state.json").read_text(encoding="utf-8"))
    assert state["review"]["week"] == week and state["review"]["path"] == out["path"]


def test_review_markdown_english_by_default(repo, capsys):
    commit_seed(repo)
    assert main(["--root", str(repo), "--json", "review", "week", "--since", "2026-10-14T00:00:00"]) == 0
    out = json.loads(capsys.readouterr().out)
    text = (repo / ".nod" / out["path"]).read_text(encoding="utf-8")
    assert not CYRILLIC.search(text)
    for head in ("What to improve", "By card", "By agent command", "Most expensive", "Least successful",
                 "Owner answers"):
        assert f"\n## {head}\n" in text
    assert "# Weekly review " in text and "\nRuns 2 · steps 1 " in text


def test_review_markdown_russian(repo, capsys):
    main(["--root", str(repo), "init"]); capsys.readouterr()
    set_lang(repo, "ru")
    commit_seed(repo)
    assert main(["--root", str(repo), "--json", "review", "week", "--since", "2026-10-14T00:00:00"]) == 0
    out = json.loads(capsys.readouterr().out)
    text = (repo / ".nod" / out["path"]).read_text(encoding="utf-8")
    for head in ("Что улучшить", "По карточкам", "По командам агентов", "Самые дорогие", "Самые неудачные",
                 "Ответы владельца"):
        assert f"\n## {head}\n" in text
    assert "# Обзор недели " in text and "\nРанов 2 · шагов 1 " in text


def test_review_week_text_output(repo, capsys):
    commit_seed(repo)
    assert main(["--root", str(repo), "review", "week", "--since", "2026-10-14T00:00:00"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Weekly review ") and "runs 2 · steps 1" in out and "What to improve:" in out
    assert out.rstrip().endswith(".md") and not CYRILLIC.search(out)


def test_review_week_text_output_in_russian(repo, capsys, monkeypatch):
    commit_seed(repo)
    monkeypatch.setenv("NOD_LANG", "ru")
    assert main(["--root", str(repo), "review", "week", "--since", "2026-10-14T00:00:00"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Обзор недели ") and "ранов 2 · шагов 1" in out and "Что улучшить:" in out


def test_review_week_on_empty_state(repo, capsys):
    main(["--root", str(repo), "init"]); capsys.readouterr()
    assert main(["--root", str(repo), "--json", "review", "week"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["runs"] == 0 and out["suggestions"] == [] and out["tokens"] == 0
    assert "No suggestions" in (repo / ".nod" / out["path"]).read_text(encoding="utf-8")


def test_review_mark_and_rerun_keeps_status(repo, capsys):
    s = seed(repo)
    s.save_decision(m.Decision(id="d-2222", kind="run-stuck", card="c-aaaa", created="2026-10-19T10:00:00",
                               question="Stuck", proposed="restart", options=["restart", "backlog"]))
    git(repo, "add", ".nod"); git(repo, "commit", "-m", "state: seed")
    main(["--root", str(repo), "--json", "review", "week", "--since", "2026-10-14T00:00:00"]); week = json.loads(capsys.readouterr().out)["week"]
    assert main(["--root", str(repo), "review", "mark", week, "1", "--applied"]) == 0
    assert "marked 1: applied" in capsys.readouterr().out
    assert s.load_review(week).suggestions[0].status == "applied"
    assert "1. [applied]" in (s.root / "reviews" / f"{week}.md").read_text(encoding="utf-8")
    main(["--root", str(repo), "--json", "review", "week", "--since", "2026-10-14T00:00:00"])
    assert json.loads(capsys.readouterr().out)["suggestions"][0]["status"] == "applied"


def test_review_mark_in_russian_after_an_english_week(repo, capsys, monkeypatch):
    """The review file is written in English, the mark runs in Russian: the heading is still found."""
    s = seed(repo)
    s.save_decision(m.Decision(id="d-2222", kind="run-stuck", card="c-aaaa", created="2026-10-19T10:00:00",
                               question="Stuck", proposed="restart", options=["restart", "backlog"]))
    git(repo, "add", ".nod"); git(repo, "commit", "-m", "state: seed")
    main(["--root", str(repo), "--json", "review", "week", "--since", "2026-10-14T00:00:00"])
    week = json.loads(capsys.readouterr().out)["week"]
    monkeypatch.setenv("NOD_LANG", "ru")
    assert main(["--root", str(repo), "review", "mark", week, "1", "--applied"]) == 0
    assert "отмечено 1: applied" in capsys.readouterr().out
    assert "1. [applied]" in (s.root / "reviews" / f"{week}.md").read_text(encoding="utf-8")


def test_review_mark_refuses_unknown(repo, capsys):
    main(["--root", str(repo), "init"]); capsys.readouterr()
    assert main(["--root", str(repo), "review", "mark", "2026-01", "1", "--applied"]) == 2
    assert 'no review "2026-01"' in capsys.readouterr().err


def test_review_week_refused_when_stale(repo, capsys, monkeypatch):
    main(["--root", str(repo), "init"]); capsys.readouterr(); enable_push(repo)
    monkeypatch.setattr(gitsync.GitSync, "pull_ff", lambda self: False)
    assert main(["--root", str(repo), "review", "week"]) == 3


def test_review_week_rejects_bad_since(repo, capsys):
    main(["--root", str(repo), "init"]); capsys.readouterr()
    assert main(["--root", str(repo), "review", "week", "--since", "yesterday"]) == 2
    assert "invalid --since date: yesterday" in capsys.readouterr().err


def test_review_week_rejects_since_with_zone(repo, capsys):
    main(["--root", str(repo), "init"]); capsys.readouterr()
    assert main(["--root", str(repo), "review", "week", "--since", "2026-10-14T00:00:00+03:00"]) == 2
    assert "invalid --since date: 2026-10-14T00:00:00+03:00" in capsys.readouterr().err


def test_review_week_rejects_since_in_future(repo, capsys):
    main(["--root", str(repo), "init"]); capsys.readouterr()
    assert main(["--root", str(repo), "review", "week", "--since", "2999-01-01T00:00:00"]) == 2
    err = capsys.readouterr().err
    assert "--since 2999-01-01T00:00:00 is not before the current time" in err
    assert not list((repo / ".nod").glob("reviews/*.md"))


def test_review_errors_in_russian(repo, capsys, monkeypatch):
    main(["--root", str(repo), "init"]); capsys.readouterr()
    monkeypatch.setenv("NOD_LANG", "ru")
    assert main(["--root", str(repo), "review", "week", "--since", "вчера"]) == 2
    assert "неверная дата --since: вчера" in capsys.readouterr().err
    assert main(["--root", str(repo), "review", "week", "--since", "2999-01-01T00:00:00"]) == 2
    assert "--since 2999-01-01T00:00:00 не раньше текущего момента" in capsys.readouterr().err
    assert main(["--root", str(repo), "review", "mark", "2026-01", "1", "--applied"]) == 2
    assert "нет обзора «2026-01»" in capsys.readouterr().err


def test_review_mark_refuses_unknown_number_and_bad_week(repo, capsys):
    main(["--root", str(repo), "init"]); capsys.readouterr()
    main(["--root", str(repo), "--json", "review", "week"]); week = json.loads(capsys.readouterr().out)["week"]
    assert main(["--root", str(repo), "review", "mark", week, "7", "--proposed"]) == 2
    assert f"review {week} has no suggestion 7" in capsys.readouterr().err
    assert main(["--root", str(repo), "review", "mark", "../x", "1", "--applied"]) == 2
    assert "invalid week" in capsys.readouterr().err
