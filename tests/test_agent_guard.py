# tests/test_agent_guard.py
"""Under the driver's agent command (`NOD_AGENT`) owner answers and closing cards are refused."""
import pytest

from the_nod.cli import main
from the_nod.driver import files

GUARD = "this command is not available to the driver's agent"


def _card(repo, capsys) -> str:
    main(["--root", str(repo), "init"])
    capsys.readouterr()
    main(["--root", str(repo), "card", "add", "Export habits to CSV"])
    return capsys.readouterr().out.strip()


@pytest.mark.parametrize("argv", [
    ["decision", "answer", "d-x", "yes"],
    ["accept", "{card}", "--level", "1", "--result", "ok"],
    ["run", "finish", "r-x", "--result", "ok"],
    ["card", "close", "{card}"],
    ["card", "return", "{card}", "--note", "not like this"],
    ["card", "move", "{card}", "--top"],
    ["driver", "once"],
    ["driver"],
    ["driver", "install", "--dry-run"],
    ["driver", "uninstall", "--dry-run"],
    ["install", "--dry-run"],
    ["install"],
    ["init"],
    ["render", "backlog", "--write", "{out}"],
])
def test_agent_cannot_act_for_owner(repo, capsys, monkeypatch, argv):
    cid = _card(repo, capsys)
    out_file = repo.parent / "planted.md"
    monkeypatch.setenv("NOD_AGENT", "1")
    code = main(["--root", str(repo), *(a.replace("{card}", cid).replace("{out}", str(out_file)) for a in argv)])
    out = capsys.readouterr()
    assert code == 2 and GUARD in out.err
    assert not out_file.exists()


def test_agent_init_creates_nothing(repo, capsys, monkeypatch):
    monkeypatch.setenv("NOD_AGENT", "1")
    assert main(["--root", str(repo), "init"]) == 2
    assert GUARD in capsys.readouterr().err
    assert not (repo / ".nod").exists() and not (repo / ".gitignore").exists()


def test_agent_may_print_the_backlog(repo, capsys, monkeypatch):
    _card(repo, capsys)
    monkeypatch.setenv("NOD_AGENT", "1")
    assert main(["--root", str(repo), "render", "backlog"]) == 0
    assert "Export habits to CSV" in capsys.readouterr().out


@pytest.mark.parametrize("kind", ["fork", "verdict", "next-batch", "return", "pain", "run-stuck", "brief-yes"])
def test_agent_asks_only_owner_action(repo, capsys, monkeypatch, kind):
    cid = _card(repo, capsys)
    monkeypatch.setenv("NOD_AGENT", "1")
    code = main(["--root", str(repo), "decision", "ask", "--kind", kind, "--question", "Keep it?",
                 "--proposed", "yes", "--option", "yes", "--option", "no", "--card", cid])
    err = capsys.readouterr().err
    assert code == 2 and "owner-action" in err
    assert not list((repo / ".nod" / "decisions").glob("*.md"))


def test_agent_keeps_working_commands(repo, capsys, monkeypatch):
    cid = _card(repo, capsys)
    monkeypatch.setenv("NOD_AGENT", "1")
    root = ["--root", str(repo)]
    assert main([*root, "card", "add", "Weekly email digest"]) == 0
    assert main([*root, "card", "show", cid]) == 0
    assert main([*root, "status"]) == 0
    assert main([*root, "decision", "list"]) == 0
    assert main([*root, "decision", "ask", "--kind", "owner-action", "--question", "Add the API key to .env",
                 "--proposed", "done", "--option", "done", "--option", "postpone", "--card", cid]) == 0
    assert main([*root, "render", "archive"]) == 0
    monkeypatch.delenv("NOD_AGENT")
    main([*root, "card", "move", cid, "--top"])
    capsys.readouterr()
    run_id = (main([*root, "run", "start", cid, "--contracts", "2"]), capsys.readouterr().out.strip())[1]
    monkeypatch.setenv("NOD_AGENT", "1")
    assert main([*root, "run", "progress", run_id, "--contracts-done", "1"]) == 0
    assert GUARD not in capsys.readouterr().err


def test_env_from_marks_agent():
    assert files.env_from({"card": "c-1"}) == {"NOD_CARD": "c-1", "NOD_AGENT": "1"}
