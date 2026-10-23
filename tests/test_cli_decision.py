import json
from the_nod.cli import main
from the_nod.store import Store

def run(repo, *args, capsys):
    code = main(["--root", str(repo), *args]); out = capsys.readouterr(); return code, out.out, out.err

def test_ask_list_answer_verdict_accept(repo, capsys):
    run(repo, "init", capsys=capsys)
    card = run(repo, "card", "add", "Экспорт", capsys=capsys)[1].strip()
    _, out, _ = run(repo, "decision", "ask", "--kind", "verdict", "--card", card, "--question", "Принять вердикт: Экспорт",
                    "--proposed", "accept", "--option", "accept", "--option", "return", capsys=capsys)
    d = out.strip()
    _, out, _ = run(repo, "--json", "decision", "list", capsys=capsys)
    assert [x["id"] for x in json.loads(out)] == [d]
    assert run(repo, "decision", "answer", d, "accept", capsys=capsys)[0] == 0
    s = Store(repo / ".nod")
    assert s.load_card(card).status == "done" and s.load_card(card).closed_by == "owner" and card not in s.order()
    assert s.load_decision(d).answered_by and run(repo, "--json", "decision", "list", capsys=capsys)[1].strip() == "[]"

def test_answer_twice_refused(repo, capsys):
    run(repo, "init", capsys=capsys)
    d = run(repo, "decision", "ask", "--kind", "fork", "--question", "Q", "--proposed", "A", "--option", "A", "--option", "B", capsys=capsys)[1].strip()
    run(repo, "decision", "answer", d, "B", capsys=capsys)
    code, _, err = run(repo, "decision", "answer", d, "A", capsys=capsys)
    assert code == 2 and "already answered" in err

def test_free_answer_needs_flag(repo, capsys):
    run(repo, "init", capsys=capsys)
    d = run(repo, "decision", "ask", "--kind", "fork", "--question", "Q", "--proposed", "A", "--option", "A", capsys=capsys)[1].strip()
    assert run(repo, "decision", "answer", d, "свой", capsys=capsys)[0] == 2
    assert run(repo, "decision", "answer", d, "свой", "--free", capsys=capsys)[0] == 0

def test_verdict_return_creates_return_decision(repo, capsys):
    run(repo, "init", capsys=capsys)
    card = run(repo, "card", "add", "Экспорт", capsys=capsys)[1].strip()
    d = run(repo, "decision", "ask", "--kind", "verdict", "--card", card, "--question", "Q", "--proposed", "accept",
            "--option", "accept", "--option", "return", capsys=capsys)[1].strip()
    run(repo, "decision", "answer", d, "return", "--note", "кнопка не там", capsys=capsys)
    s = Store(repo / ".nod")
    assert s.load_card(card).status == "returned"
    assert [x.kind for x in s.decisions() if x.answer is None] == ["return"]

def test_list_empty_and_ask_errors(repo, capsys):
    run(repo, "init", capsys=capsys)
    assert run(repo, "decision", "list", capsys=capsys)[1].strip() == "empty"
    assert run(repo, "--json", "decision", "list", capsys=capsys)[1].strip() == "[]"
    assert run(repo, "decision", "ask", "--kind", "bogus", "--question", "Q", "--proposed", "A", capsys=capsys)[0] == 2
    code, _, err = run(repo, "decision", "ask", "--kind", "fork", "--card", "c-nope", "--question", "Q", "--proposed", "A", capsys=capsys)
    assert code == 2 and "Traceback" not in err
