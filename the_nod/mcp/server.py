"""The MCP protocol over stdio: JSON-RPC 2.0 line by line, calls are `nod` commands with `--json`.

The server describes itself in the language it started in (`start_lang`); the commands it runs answer in the
language of their own state, resolved again on every call.
"""

import contextlib
import io
import json
from pathlib import Path
from typing import BinaryIO

from the_nod import __version__, cli, harness, i18n
from the_nod.i18n import t
from the_nod.mcp.tools import MissingArgument, build, by_name_for, say

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "nod", "version": __version__}
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
EXIT_ERROR = 2


def start_lang(root: str | None) -> str:
    """The language of the tool list: NOD_LANG, then `lang` of the manifest of the state found at start, then English.

    A manifest that does not read is left to the calls, which report it; the list falls back to English.
    """
    try:
        manifest = harness.read_lang(Path(root)) if root is not None else None
    except harness.HarnessError:
        manifest = None
    return i18n.resolve(manifest)


def call_cli(root: str | None, argv: list[str]) -> tuple[int, str, str]:
    """A `nod` command in this process: the exit code and the captured stdout and stderr.

    Without `root` the `--root` flag is not passed: the core looks for the state on every call.
    """
    root_args = ["--root", root] if root is not None else []
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main([*root_args, "--json", *argv])
        except SystemExit as exit_:  # argparse refused
            code = exit_.code if isinstance(exit_.code, int) else EXIT_ERROR
        except Exception as error:  # noqa: BLE001 — a command must not take the server down
            print(t("cli.error", message=error), file=err)
            code = EXIT_ERROR
    return code, out.getvalue(), err.getvalue()


def _error(id_: object, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _result(id_: object, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _text(text: str, is_error: bool) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _initialize(params: dict) -> dict:
    asked = params.get("protocolVersion")
    version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
    return {"protocolVersion": version, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}


def _list(lang: str) -> dict:
    return {"tools": [{"name": tool.name, "description": tool.description, "inputSchema": tool.schema}
                      for tool in build(lang)]}


def _call(id_: object, params: dict, root: str | None, lang: str) -> dict:
    """`tools/call`: the tool's argv and the command; command errors go in the result, not in the protocol."""
    tool = by_name_for(lang).get(params.get("name"))
    if tool is None:
        return _error(id_, INVALID_PARAMS, say(lang, "mcp.unknown_tool", name=params.get("name")))
    try:
        argv = tool.argv(params.get("arguments") or {})
    except MissingArgument as err:
        return _result(id_, _text(str(err), True))
    code, out, err = call_cli(root, argv)
    return _result(id_, _text(out.strip() or err.strip(), code != 0))


def handle(message: object, root: str | None, lang: str = i18n.DEFAULT) -> dict | None:
    """The answer to one JSON-RPC message, in `lang`; `None` for a notification."""
    if not isinstance(message, dict):
        return _error(None, INVALID_REQUEST, say(lang, "mcp.bad_request"))
    if "id" not in message:
        return None
    id_ = message["id"]
    if message.get("jsonrpc") != "2.0":
        return _error(id_, INVALID_REQUEST, say(lang, "mcp.bad_jsonrpc"))
    method = message.get("method")
    params = message.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _error(id_, INVALID_PARAMS, say(lang, "mcp.bad_params"))
    if method == "initialize":
        return _result(id_, _initialize(params))
    if method == "ping":
        return _result(id_, {})
    if method == "tools/list":
        return _result(id_, _list(lang))
    if method == "tools/call":
        return _call(id_, params, root, lang)
    return _error(id_, METHOD_NOT_FOUND, say(lang, "mcp.unknown_method", method=method))


def _answer(line: bytes, root: str | None, lang: str) -> dict | None:
    """The answer to one line of the stream: JSON parsing, a refusal of batches, then `handle`."""
    try:
        message = json.loads(line.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as err:
        return _error(None, PARSE_ERROR, say(lang, "mcp.parse_error", error=err))
    if isinstance(message, list):
        return _error(None, INVALID_REQUEST, say(lang, "mcp.no_batches"))
    return handle(message, root, lang)


def serve(root: str | None, stdin: BinaryIO, stdout: BinaryIO, *, lang: str | None = None) -> int:
    """The server loop: a request line, an answer line; EOF ends it with code 0.

    `lang` is the language of the server's own texts and tool list; by default `start_lang(root)`.
    """
    lang = start_lang(root) if lang is None else lang
    for line in stdin:
        if not line.strip():
            continue
        response = _answer(line, root, lang)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")
            stdout.flush()
    return 0
