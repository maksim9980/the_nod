import argparse
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from the_nod import __version__, cli, i18n
from the_nod.cli import main
from the_nod.commands import mcp as mcp_command
from the_nod.context import CliError
from the_nod.mcp import server, tools
from the_nod.mcp.server import call_cli, handle, serve
from the_nod.mcp.tools import TOOLS, MissingArgument, by_name
from tests.driver_helpers import REPO_ROOT

CYRILLIC = re.compile(r"[Ѐ-ӿ]")
TOOL_NAMES = ["status", "card_add", "card_move", "card_close", "card_return", "card_show", "decision_list",
              "decision_ask", "decision_answer", "run_start", "run_progress", "run_finish", "accept", "review_week",
              "review_mark", "doctor"]


def child_env(**extra) -> dict:
    """The environment of a server subprocess: no NOD_LANG unless the test passes it."""
    env = {k: v for k, v in os.environ.items() if k != i18n.ENV}
    return {**env, "PYTHONPATH": str(REPO_ROOT), "PYTHONIOENCODING": "utf-8", **extra}


def rpc(*requests: dict) -> bytes:
    return ("\n".join(json.dumps(r, ensure_ascii=False) for r in requests) + "\n").encode("utf-8")


def listed(root, **kw) -> list[dict]:
    """The `tools/list` answer of an in-process server started on `root`."""
    out = io.BytesIO()
    assert serve(root, io.BytesIO(rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})), out, **kw) == 0
    return json.loads(out.getvalue().decode("utf-8"))["result"]["tools"]


def description(tool_list: list[dict], name: str) -> str:
    return next(t["description"] for t in tool_list if t["name"] == name)


def set_lang(repo, value: str) -> None:
    path = repo / ".nod" / "harness.toml"
    path.write_text(re.sub(r'(?m)^lang = ".*"$', f'lang = "{value}"', path.read_text(encoding="utf-8")),
                    encoding="utf-8")


def test_tools_list_names_and_schemas():
    assert [t.name for t in TOOLS] == TOOL_NAMES
    assert all(t.schema["type"] == "object" and "properties" in t.schema for t in TOOLS)
    assert by_name["card_add"].argv({"title": "Export habits", "top": True}) == ["card", "add", "--top", "--", "Export habits"]
    assert by_name["accept"].argv({"card": "c-1", "level": 2, "result": "solved", "frames": [{"path": "a.png", "caption": "x"}]}) == ["accept", "--level", "2", "--result", "solved", "--frame", "a.png", "--caption", "x", "--", "c-1"]
    with pytest.raises(MissingArgument, match="note"):
        by_name["card_return"].argv({"id": "c-1"})
    with pytest.raises(MissingArgument, match="top"):
        by_name["card_move"].argv({"id": "c-1"})


def test_builders_cover_options_and_types():
    assert by_name["status"].argv({"no_sync": True, "since": "2026-10-01"}) == ["status", "--peek", "--no-sync", "--since", "2026-10-01"]
    assert by_name["status"].argv({}) == ["status", "--peek"]
    assert by_name["card_move"].argv({"id": "-x", "after": "c-2"}) == ["card", "move", "--after", "c-2", "--", "-x"]
    assert by_name["decision_ask"].argv({"kind": "fork", "question": "Q", "proposed": "a", "options": ["a", "b"]}) == ["decision", "ask", "--kind", "fork", "--question", "Q", "--proposed", "a", "--option", "a", "--option", "b"]
    assert by_name["decision_answer"].argv({"id": "d-1", "answer": "-a", "free": True}) == ["decision", "answer", "--free", "--", "d-1", "-a"]
    assert by_name["run_finish"].argv({"id": "r-1", "result": "ok", "tokens": 5}) == ["run", "finish", "--result", "ok", "--tokens", "5", "--", "r-1"]
    assert by_name["review_mark"].argv({"week": "2026-43", "n": 2, "status": "applied"}) == ["review", "mark", "--applied", "--", "2026-43", "2"]
    assert by_name["decision_list"].argv({"all": True}) == ["decision", "list", "--all"]
    assert by_name["doctor"].argv({}) == ["doctor"]
    with pytest.raises(MissingArgument, match="exactly one"):
        by_name["card_move"].argv({"id": "c-1", "top": True, "bottom": True})
    with pytest.raises(MissingArgument, match="level"):
        by_name["accept"].argv({"card": "c-1", "level": "2", "result": "x"})
    with pytest.raises(MissingArgument, match="options"):
        by_name["decision_ask"].argv({"kind": "fork", "question": "Q", "proposed": "a", "options": "a"})
    with pytest.raises(MissingArgument, match="frames"):
        by_name["accept"].argv({"card": "c-1", "level": 1, "result": "x", "frames": [{"path": "a"}]})
    with pytest.raises(MissingArgument, match="status"):
        by_name["review_mark"].argv({"week": "w", "n": 1, "status": "x"})


def test_schemas_are_closed_and_described():
    for tool in TOOLS:
        assert tool.schema["additionalProperties"] is False and tool.description
        assert all("type" in p and p["description"] for p in tool.schema["properties"].values())
        assert set(tool.schema.get("required", [])) <= set(tool.schema["properties"])


# --- the tools follow the language ---

def descriptions(schema) -> list[str]:
    """Every `description` in a schema, however deep."""
    if isinstance(schema, dict):
        found = [schema["description"]] if "description" in schema else []
        return found + [text for value in schema.values() for text in descriptions(value)]
    if isinstance(schema, list):
        return [text for value in schema for text in descriptions(value)]
    return []


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_every_tool_and_argument_is_described_in_each_language(lang):
    built = tools.build(lang)
    assert [t.name for t in built] == TOOL_NAMES
    for tool in built:
        texts = [tool.description, *descriptions(tool.schema)]
        assert all(text.strip() for text in texts), tool.name
        assert all(bool(CYRILLIC.search(text)) == (lang == "ru") for text in texts), (tool.name, lang)


def test_argv_does_not_depend_on_the_language():
    args = {"card": "c-1", "level": 2, "result": "solved", "steps": ["a"], "frames": [{"path": "p", "caption": "c"}]}
    assert tools.by_name_for("ru")["accept"].argv(args) == by_name["accept"].argv(args)
    assert [(t.name, t.schema.get("required")) for t in tools.build("ru")] == [(t.name, t.schema.get("required")) for t in TOOLS]


def test_argument_errors_follow_the_tool_language():
    ru = tools.by_name_for("ru")
    with pytest.raises(MissingArgument, match="нет аргумента «note»"):
        ru["card_return"].argv({"id": "c-1"})
    with pytest.raises(MissingArgument, match="ровно один из top, bottom, before, after"):
        ru["card_move"].argv({"id": "c-1"})
    with pytest.raises(MissingArgument, match="неверного типа"):
        ru["accept"].argv({"card": "c-1", "level": "2", "result": "x"})
    with pytest.raises(MissingArgument, match="лишний аргумент «zzz»"):
        ru["card_show"].argv({"id": "c-1", "zzz": 1})
    with pytest.raises(MissingArgument, match="аргументы должны быть объектом"):
        ru["card_show"].argv([])


def test_argument_errors_in_english():
    with pytest.raises(MissingArgument, match='missing argument "note"'):
        by_name["card_return"].argv({"id": "c-1"})
    with pytest.raises(MissingArgument, match='argument "level" has the wrong type'):
        by_name["accept"].argv({"card": "c-1", "level": "2", "result": "x"})
    with pytest.raises(MissingArgument, match='extra argument "zzz"'):
        by_name["card_show"].argv({"id": "c-1", "zzz": 1})
    with pytest.raises(MissingArgument, match="arguments must be an object"):
        by_name["card_show"].argv([])
    with pytest.raises(MissingArgument, match="card_move: exactly one of top, bottom, before, after"):
        by_name["card_move"].argv({"id": "c-1"})


def test_mcp_tool_descriptions_follow_lang(monkeypatch):
    """No variable: English. NOD_LANG=ru: Russian. The start language, not the language of a later call."""
    english = listed(None)
    assert description(english, "status") == "Snapshot of the state: what waits for the owner, what is running, the backlog."
    assert not CYRILLIC.search(json.dumps(english, ensure_ascii=False))
    monkeypatch.setenv("NOD_LANG", "ru")
    russian = listed(None)
    assert description(russian, "status") == "Снимок состояния: что ждёт владельца, что бежит, бэклог."
    assert all(CYRILLIC.search(t["description"]) for t in russian)


def test_mcp_tool_descriptions_follow_the_manifest(repo, capsys, monkeypatch):
    main(["--root", str(repo), "init"]); capsys.readouterr()
    state = str(repo / ".nod")
    assert not CYRILLIC.search(description(listed(state), "status"))
    set_lang(repo, "ru")
    assert CYRILLIC.search(description(listed(state), "status"))
    monkeypatch.setenv("NOD_LANG", "en")  # the variable wins over the manifest
    assert not CYRILLIC.search(description(listed(state), "status"))


def test_mcp_broken_manifest_lists_english_tools(repo, capsys):
    main(["--root", str(repo), "init"]); capsys.readouterr()
    set_lang(repo, "fr")
    assert not CYRILLIC.search(description(listed(str(repo / ".nod")), "status"))


def test_tools_list_keeps_the_start_language_after_a_call_in_another(monkeypatch):
    """Each call switches the process language to its state's; the list must not follow it."""
    monkeypatch.setattr(server, "call_cli", lambda root, argv: i18n.use("ru") or (0, "{}", ""))
    out = io.BytesIO()
    serve(None, io.BytesIO(rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "card_show", "arguments": {"id": "c-1"}}},
                               {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})), out)
    answers = [json.loads(line) for line in out.getvalue().decode("utf-8").splitlines()]
    assert i18n.current() == "ru" and not CYRILLIC.search(description(answers[1]["result"]["tools"], "status"))


def test_mcp_subprocess_descriptions_follow_lang(tmp_path):
    requests = rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    for env, expected in (({}, False), ({"NOD_LANG": "ru"}, True)):
        proc = subprocess.run([sys.executable, "-m", "the_nod", "mcp"], input=requests, capture_output=True, cwd=tmp_path,
                              timeout=120, env=child_env(**env))
        answer = json.loads(proc.stdout.decode("utf-8"))
        assert proc.returncode == 0
        assert bool(CYRILLIC.search(description(answer["result"]["tools"], "status"))) is expected


# --- the tools against the CLI ---

def sample_args(tool) -> dict:
    """Arguments that fill every property of the tool's schema."""
    values = {"boolean": True, "integer": 1, "string": "x"}
    args = {}
    for key, prop in tool.schema["properties"].items():
        if "enum" in prop:
            args[key] = prop["enum"][0]
        elif prop["type"] == "array":
            args[key] = [{"path": "p", "caption": "c"}] if prop["items"]["type"] == "object" else ["x"]
        else:
            args[key] = values[prop["type"]]
    if tool.name == "card_move":  # exactly one place
        args = {"id": "c-1", "top": True}
    return args


def cli_flags(path: list[str]) -> set[str]:
    """The option strings of the subcommand at `path` in the real parser."""
    parser = cli.build_parser()
    for word in path:
        sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        parser = sub.choices[word]
    return {option for action in parser._actions for option in action.option_strings}


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_every_tool_flag_exists_in_the_cli(tool):
    argv = tool.argv(sample_args(tool))
    command = argv[:argv.index("--")] if "--" in argv else argv
    flags = {word for word in command if word.startswith("--")}
    path = command_path(command)
    assert path, tool.name
    assert flags <= cli_flags(path), (tool.name, sorted(flags - cli_flags(path)))


def subcommands(path: list[str]) -> set[str]:
    parser = cli.build_parser()
    for word in path:
        sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        parser = sub.choices[word]
    sub = next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)
    return set(sub.choices) if sub else set()


def command_path(command: list[str]) -> list[str]:
    """The leading subcommand words of an argv: `["card", "add", "--top"]` gives `["card", "add"]`."""
    path: list[str] = []
    for word in command:
        if word in subcommands(path):
            path.append(word)
        else:
            break
    return path


def test_doctor_tool_has_no_options():
    """The old `nod` option mapped to a flag the CLI never had."""
    assert by_name["doctor"].schema["properties"] == {}
    with pytest.raises(MissingArgument, match="nod"):
        by_name["doctor"].argv({"nod": "D:/x"})
    assert "--nod" not in cli_flags(["doctor"])


def test_mcp_review_mark_status_values():
    mark = by_name["review_mark"]
    assert mark.schema["properties"]["status"]["enum"] == ["applied", "proposed"]
    assert mark.argv({"week": "2026-43", "n": 1, "status": "proposed"}) == ["review", "mark", "--proposed", "--", "2026-43", "1"]
    for old in ("внесено", "предлагается"):
        with pytest.raises(MissingArgument):
            mark.argv({"week": "2026-43", "n": 1, "status": old})
    assert tools.by_name_for("ru")["review_mark"].schema["properties"]["status"]["enum"] == ["applied", "proposed"]


# --- the protocol ---

def test_handle_initialize_list_call(monkeypatch):
    monkeypatch.setattr(server, "call_cli", lambda root, argv: (0, '{"id": "c-aaaa"}', ""))
    init = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}, "R")
    assert init["result"]["protocolVersion"] == "2025-03-26" and init["result"]["capabilities"] == {"tools": {}}
    assert handle({"jsonrpc": "2.0", "id": 9, "method": "initialize", "params": {"protocolVersion": "1999"}}, "R")["result"]["protocolVersion"] == "2025-06-18"
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, "R") is None
    assert handle({"jsonrpc": "2.0", "id": 7, "method": "ping"}, "R") == {"jsonrpc": "2.0", "id": 7, "result": {}}
    listed_tools = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, "R")["result"]["tools"]
    assert listed_tools[1]["name"] == "card_add" and "inputSchema" in listed_tools[1]
    called = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "card_add", "arguments": {"title": "Export habits"}}}, "R")
    assert called["result"] == {"content": [{"type": "text", "text": '{"id": "c-aaaa"}'}], "isError": False}
    missing = handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "card_return", "arguments": {"id": "c-1"}}}, "R")
    assert missing["result"]["isError"] is True and "note" in missing["result"]["content"][0]["text"]


def test_server_info_version_is_the_package_version():
    info = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, "R")["result"]["serverInfo"]
    assert info == {"name": "nod", "version": __version__}


def test_handle_call_passes_root_and_uses_stderr_on_failure(monkeypatch):
    seen = []
    monkeypatch.setattr(server, "call_cli", lambda root, argv: seen.append((root, argv)) or (2, "", "error: no such card\n"))
    called = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "card_show", "arguments": {"id": "c-1"}}}, "R")
    assert called["result"] == {"content": [{"type": "text", "text": "error: no such card"}], "isError": True}
    assert seen == [("R", ["card", "show", "--", "c-1"])]


def test_handle_parse_error_and_unknown_method():
    assert handle({"jsonrpc": "2.0", "id": 5, "method": "nope"}, "R")["error"]["code"] == -32601
    assert handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "install"}}, "R")["error"]["code"] == -32602
    assert handle({"jsonrpc": "1.0", "id": 8, "method": "ping"}, "R")["error"]["code"] == -32600
    assert handle([1, 2], "R")["error"]["code"] == -32600 and handle([1, 2], "R")["id"] is None
    out = io.BytesIO(); assert serve("R", io.BytesIO(b"{not json\n"), out, lang="en") == 0
    err = json.loads(out.getvalue().decode("utf-8")); assert err["error"]["code"] == -32700 and err["id"] is None


def test_protocol_error_texts_english():
    texts = {
        "unknown tool": handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "install"}}, "R"),
        "unknown method": handle({"jsonrpc": "2.0", "id": 2, "method": "nope"}, "R"),
        "jsonrpc": handle({"jsonrpc": "1.0", "id": 3, "method": "ping"}, "R"),
        "params": handle({"jsonrpc": "2.0", "id": 4, "method": "ping", "params": 5}, "R"),
        "request": handle([1], "R"),
    }
    messages = {key: answer["error"]["message"] for key, answer in texts.items()}
    assert messages == {"unknown tool": 'unknown tool "install"', "unknown method": 'method "nope" is not supported',
                        "jsonrpc": 'jsonrpc "2.0" is required', "params": "params must be an object",
                        "request": "expected a request object"}
    out = io.BytesIO()
    serve("R", io.BytesIO(b"{not json\n[1]\n"), out, lang="en")
    parse, batch = [json.loads(line)["error"]["message"] for line in out.getvalue().decode("utf-8").splitlines()]
    assert parse.startswith("JSON parse error: ") and batch == "request batches are not supported"


def test_protocol_error_texts_follow_the_server_language():
    answer = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "install"}}, "R", lang="ru")
    assert answer["error"]["message"] == "неизвестный инструмент «install»"
    assert handle({"jsonrpc": "2.0", "id": 2, "method": "nope"}, "R", lang="ru")["error"]["message"] == "метод «nope» не поддерживается"
    out = io.BytesIO()
    serve("R", io.BytesIO(b"[1]\n"), out, lang="ru")
    assert json.loads(out.getvalue().decode("utf-8"))["error"]["message"] == "пакеты запросов не поддерживаются"
    missing = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "card_return", "arguments": {"id": "c-1"}}}, "R", lang="ru")
    assert missing["result"]["content"][0]["text"] == "нет аргумента «note»"


def test_mcp_error_texts_english(tmp_path, monkeypatch):
    """The core answers in English: the MCP client reads the same texts as the CLI."""
    monkeypatch.chdir(tmp_path)
    called = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "status", "arguments": {"no_sync": True}}}, None)
    assert called["result"]["isError"] is True
    assert called["result"]["content"][0]["text"] == "error: no state: run nod init"
    monkeypatch.setenv("NOD_AGENT", "1")
    refused = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "decision_answer", "arguments": {"id": "d-1", "answer": "yes"}}}, None)
    assert refused["result"]["isError"] is True
    assert "this command is not available to the driver's agent" in refused["result"]["content"][0]["text"]


def test_call_cli_unexpected_error_text(monkeypatch):
    def boom(argv):
        raise RuntimeError("boom")

    monkeypatch.setattr(server.cli, "main", boom)
    assert call_cli(None, ["status"]) == (2, "", "error: boom\n")
    i18n.use("ru")
    assert call_cli(None, ["status"]) == (2, "", "ошибка: boom\n")


def test_serve_skips_blank_lines_and_rejects_batches():
    out = io.BytesIO()
    assert serve("R", io.BytesIO(b"\n  \n[1]\n" + b'{"jsonrpc": "2.0", "id": 1, "method": "ping"}\n'), out) == 0
    answers = [json.loads(l) for l in out.getvalue().decode("utf-8").splitlines()]
    assert [a.get("error", {}).get("code") for a in answers] == [-32600, None] and answers[1]["result"] == {}


def test_call_cli_captures_json_and_argparse_errors(repo):
    main(["--root", str(repo), "init"])
    code, out, err = call_cli(str(repo / ".nod"), ["card", "add", "Export habits"])
    assert code == 0 and json.loads(out)["id"].startswith("c-")
    code, out, err = call_cli(str(repo / ".nod"), ["card", "bogus"])
    assert code == 2 and "invalid choice" in err and out == ""


def test_mcp_subprocess_roundtrip(repo, tmp_path):
    main(["--root", str(repo), "init"])
    proc = subprocess.Popen([sys.executable, "-m", "the_nod", "--root", str(repo), "mcp"], cwd=tmp_path, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=child_env())
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
             {"jsonrpc": "2.0", "method": "notifications/initialized"},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
             {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "card_add", "arguments": {"title": "Ёлочки «»"}}},  # non-ASCII must survive the round trip
             {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "status", "arguments": {"no_sync": True}}}]
    payload = "\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\nnot json\n"
    out, err = proc.communicate(payload.encode("utf-8"), timeout=120)
    answers = [json.loads(l) for l in out.decode("utf-8").splitlines() if l.strip()]
    assert proc.returncode == 0 and [a.get("id") for a in answers] == [1, 2, 3, 4, None]
    assert "\\u" not in out.decode("utf-8") and "c-" in answers[2]["result"]["content"][0]["text"]
    assert "Ёлочки «»" in answers[3]["result"]["content"][0]["text"] and answers[4]["error"]["code"] == -32700


def test_mcp_starts_without_state(tmp_path):
    """A folder without .nod and git: initialize and tools/list answer, tools/call status is isError with the core text."""
    requests = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
                   {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                   {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "status", "arguments": {"no_sync": True}}})
    proc = subprocess.run([sys.executable, "-m", "the_nod", "mcp"], input=requests, capture_output=True, cwd=tmp_path, timeout=120,
                          env=child_env())
    answers = [json.loads(l) for l in proc.stdout.decode("utf-8").splitlines() if l.strip()]
    assert proc.returncode == 0 and answers[0]["result"]["serverInfo"]["version"] == __version__
    assert len(answers[1]["result"]["tools"]) == len(TOOLS)
    assert answers[2]["result"]["isError"] is True and "no state: run nod init" in answers[2]["result"]["content"][0]["text"]


def test_call_cli_without_root_omits_flag(monkeypatch):
    seen = []
    monkeypatch.setattr(server.cli, "main", lambda argv: seen.append(argv) or 0)
    server.call_cli(None, ["status"])
    server.call_cli("D:/x/.nod", ["status"])
    assert seen == [["--json", "status"], ["--root", "D:/x/.nod", "--json", "status"]]


def test_mcp_explicit_root_missing_exits_2(tmp_path):
    """An explicit --root to nowhere is refused with code 2 instead of a silent search for the state from cwd."""
    proc = subprocess.run([sys.executable, "-m", "the_nod", "--root", str(tmp_path / "nowhere"), "mcp"], input=b"", capture_output=True, cwd=tmp_path, timeout=120,
                          env=child_env())
    assert proc.returncode == 2 and "no state" in proc.stderr.decode("utf-8")


def test_root_swallows_refusal_only_without_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert mcp_command._root(None) is None
    with pytest.raises(CliError):
        mcp_command._root(str(tmp_path / "nowhere"))


# --- the catalog and the code agree ---

MCP_KEY = re.compile(r"""["'](mcp\.[a-z0-9_]+)["']""")
MCP_DIR = Path(__file__).resolve().parent.parent / "the_nod" / "mcp"


def test_mcp_keys_used_in_code_exist_and_every_key_is_used():
    used = {key for path in MCP_DIR.glob("*.py") for key in MCP_KEY.findall(path.read_text(encoding="utf-8"))}
    defined = {key for key in i18n.catalog("en") if key.startswith("mcp.")}
    assert used and sorted(used - defined) == [] and sorted(defined - used) == []
