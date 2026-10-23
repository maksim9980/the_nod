import json, re
from the_nod.cli import main

def test_write_commands_answer_json(repo, capsys):
    assert main(["--root", str(repo), "--json", "init"]) == 0 and json.loads(capsys.readouterr().out)["created"].endswith(".nod")
    main(["--root", str(repo), "--json", "card", "add", "Ёлочки «»"]); cid = json.loads(capsys.readouterr().out)["id"]
    assert main(["--root", str(repo), "card", "move", cid, "--top", "--json"]) == 0 and json.loads(capsys.readouterr().out) == {"ok": True}
    main(["--root", str(repo), "--json", "decision", "ask", "--kind", "fork", "--question", "Q?", "--proposed", "a", "--option", "a"]); did = json.loads(capsys.readouterr().out)["id"]
    assert main(["--root", str(repo), "--json", "decision", "answer", did, "a"]) == 0 and json.loads(capsys.readouterr().out) == {"ok": True}
    main(["--root", str(repo), "--json", "run", "start", cid]); rid = json.loads(capsys.readouterr().out)["id"]
    assert main(["--root", str(repo), "--json", "run", "finish", rid, "--result", "ok"]) == 0 and json.loads(capsys.readouterr().out) == {"ok": True}

def test_text_output_unchanged(repo, capsys):
    main(["--root", str(repo), "init"]); assert capsys.readouterr().out.startswith("created .nod")
    main(["--root", str(repo), "card", "add", "A"]); assert re.fullmatch(r"c-[0-9a-z]{4}\n", capsys.readouterr().out)
