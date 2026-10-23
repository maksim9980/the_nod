import json, subprocess

import pytest
from the_nod.cli import main
from the_nod.store import Store
from tests.conftest import enable_push

def run(repo, *args, capsys):
    code = main(["--root", str(repo), *args]); out = capsys.readouterr(); return code, out.out, out.err

def test_init_creates_layout_and_gitignore(repo, capsys):
    code, out, _ = run(repo, "init", capsys=capsys)
    assert code == 0 and (repo / ".nod" / "harness.toml").exists() and (repo / ".nod" / "order.md").exists()
    assert ".nod/state.json" in (repo / ".gitignore").read_text(encoding="utf-8")
    assert run(repo, "init", capsys=capsys)[0] == 0


@pytest.mark.parametrize("lang, line", [
    ("en", ".gitignore updated, not committed: commit it yourself"),
    ("ru", ".gitignore дополнен и не закоммичен: закоммить его сам"),
])
def test_init_says_gitignore_is_not_committed(repo, capsys, monkeypatch, lang, line):
    """The field test: `nod init` left the `.gitignore` edit uncommitted and said nothing."""
    monkeypatch.setenv("NOD_LANG", lang)
    code, out, _ = run(repo, "init", capsys=capsys)
    assert code == 0 and out.splitlines()[1:] == [line]
    status = subprocess.run(["git", "status", "--short", "--", ".gitignore"], cwd=repo, capture_output=True,
                            text=True, encoding="utf-8").stdout
    assert status.strip()  # the line tells the truth: the file is changed and not committed
    assert run(repo, "init", capsys=capsys)[1].splitlines()[1:] == []  # nothing new to add: no line

def test_add_and_order_and_commit(repo, capsys):
    run(repo, "init", capsys=capsys)
    _, out, _ = run(repo, "card", "add", "Двигать срок", capsys=capsys); a = out.strip()
    _, out, _ = run(repo, "card", "add", "Срочное", "--top", capsys=capsys); b = out.strip()
    assert Store(repo / ".nod").order() == [b, a]
    log = subprocess.run(["git", "log", "--format=%s", "-3"], cwd=repo, capture_output=True, text=True, encoding="utf-8").stdout
    assert f"state: card add {b}" in log

def test_add_writes_each_id_once_into_order_md(repo, capsys):
    """`order()` already lists a saved card that is missing from the file: reading it after the save doubled the id."""
    run(repo, "init", capsys=capsys)
    a = run(repo, "card", "add", "Export habits to CSV", capsys=capsys)[1].strip()
    b = run(repo, "card", "add", "Weekly email digest", "--top", capsys=capsys)[1].strip()
    c = run(repo, "card", "add", "Dark mode for the habit grid", capsys=capsys)[1].strip()
    lines = (repo / ".nod" / "order.md").read_text(encoding="utf-8").splitlines()
    ids = [line.split()[0] for line in lines if line.strip() and not line.startswith("#")]
    assert ids == [b, a, c]

def test_move_close_return(repo, capsys):
    run(repo, "init", capsys=capsys)
    ids = [run(repo, "card", "add", t, capsys=capsys)[1].strip() for t in ("A", "B", "C")]
    run(repo, "card", "move", ids[2], "--before", ids[0], capsys=capsys)
    s = Store(repo / ".nod"); assert s.order() == [ids[2], ids[0], ids[1]]
    run(repo, "card", "close", ids[1], capsys=capsys)
    assert s.load_card(ids[1]).status == "done" and s.load_card(ids[1]).closed_by == "owner" and ids[1] not in s.order()
    run(repo, "card", "return", ids[0], "--note", "не та дата", capsys=capsys)
    d = s.decisions()[0]; assert d.kind == "return" and d.card == ids[0] and d.note == "не та дата"

def test_write_refused_when_stale(repo, capsys, monkeypatch):
    run(repo, "init", capsys=capsys); enable_push(repo)
    from the_nod import gitsync; monkeypatch.setattr(gitsync.GitSync, "pull_ff", lambda self: False)
    code, _, err = run(repo, "card", "add", "X", capsys=capsys)
    assert code == 3 and "has been stale" in err

def test_show_text_and_json(repo, capsys):
    run(repo, "init", capsys=capsys)
    cid = run(repo, "card", "add", "Показать", "--body", "тело", capsys=capsys)[1].strip()
    _, out, _ = run(repo, "card", "show", cid, capsys=capsys)
    assert "Показать" in out and "backlog" in out and "тело" in out
    meta = json.loads(run(repo, "--json", "card", "show", cid, capsys=capsys)[1])
    assert meta["id"] == cid and meta["body"] == "тело"
    code, _, err = run(repo, "card", "show", "c-zzzz", capsys=capsys)
    assert code == 2 and "c-zzzz" in err

def test_detached_head_refused_before_write(repo, capsys):
    run(repo, "init", capsys=capsys)
    subprocess.run(["git", "checkout", "--detach"], cwd=repo, capture_output=True, check=True)
    code, _, err = run(repo, "card", "add", "X", capsys=capsys)
    assert code == 2 and "not on a branch: detached HEAD" in err
    assert not list((repo / ".nod" / "cards").glob("*.md"))
