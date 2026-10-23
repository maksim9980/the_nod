"""MCP tools: name, description, argument schema and the argv of the `nod` command.

The descriptions follow a language chosen when the tools are built (`build`): the server describes itself
in the language it started in, however later calls switch the language of the process.
"""

from dataclasses import dataclass
from functools import cache, partial
from typing import Callable

from the_nod import i18n, vocab
from the_nod.model import ACCEPT_RESULTS

MARK_FLAGS = {vocab.APPLIED: "--applied", vocab.PROPOSED: "--proposed"}
PLACES = ("top", "bottom", "before", "after")


class MissingArgument(ValueError):
    """The tool arguments do not fit: a required one is missing, a wrong type, an extra key."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict
    argv: Callable[[dict], list[str]]


@dataclass(frozen=True)
class Field:
    """A tool argument: the flag of an option or a positional value."""
    key: str
    kind: str  # string | integer | boolean | strings | frames | mark
    description: str
    flag: str | None = None
    required: bool = False

    @property
    def positional(self) -> bool:
        """A string or a number without a flag: the value goes after `--`."""
        return self.flag is None and self.kind in ("string", "integer")


def say(lang: str, key: str, /, **values: object) -> str:
    """Message `key` in `lang`, not in the language of the moment: the server keeps its start language."""
    return i18n.catalog(lang)[key].format(**values)


def _frame_ok(item: object) -> bool:
    return isinstance(item, dict) and set(item) == {"path", "caption"} \
        and all(isinstance(v, str) for v in item.values())


_VALID = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "strings": lambda v: isinstance(v, list) and all(isinstance(s, str) for s in v),
    "frames": lambda v: isinstance(v, list) and all(_frame_ok(f) for f in v),
    "mark": lambda v: v in MARK_FLAGS,
}


def _value(lang: str, field: Field, args: dict) -> object:
    """An argument value, its type checked; `None` when an optional one is absent."""
    if field.key not in args:
        if field.required:
            raise MissingArgument(say(lang, "mcp.missing_arg", key=field.key))
        return None
    value = args[field.key]
    if not _VALID[field.kind](value):
        raise MissingArgument(say(lang, "mcp.bad_type", key=field.key))
    return value


def _option(field: Field, value: object) -> list[str]:
    """An option value as a piece of argv."""
    if field.kind == "boolean":
        return [field.flag] if value else []
    if field.kind == "integer":
        return [field.flag, str(int(value))]
    if field.kind == "strings":
        return [part for item in value for part in (field.flag, item)]
    if field.kind == "frames":
        return [p for f in value for p in ("--frame", f["path"], "--caption", f["caption"])]
    if field.kind == "mark":
        return [MARK_FLAGS[value]]
    return [field.flag, value]


def _build(lang: str, prefix: tuple[str, ...], fields: tuple[Field, ...],
           check: Callable[[dict], None] | None, args: dict) -> list[str]:
    """The argv: the prefix, the options, then `--` and the positionals, if there are any."""
    if not isinstance(args, dict):
        raise MissingArgument(say(lang, "mcp.args_not_object"))
    extra = sorted(set(args) - {f.key for f in fields})
    if extra:
        raise MissingArgument(say(lang, "mcp.extra_arg", key=extra[0]))
    if check is not None:
        check(args)
    options: list[str] = []
    positionals: list[str] = []
    for field in fields:
        value = _value(lang, field, args)
        if value is None:
            continue
        if field.positional:
            positionals.append(str(int(value)) if field.kind == "integer" else value)
        else:
            options += _option(field, value)
    return [*prefix, *options, *(["--", *positionals] if positionals else [])]


def _one_place(lang: str, args: dict) -> None:
    """`card_move`: exactly one of the places."""
    if isinstance(args, dict) and sum(1 for k in PLACES if args.get(k) not in (None, False)) != 1:
        raise MissingArgument(say(lang, "mcp.need_one_place"))


_JSON_TYPES = {"string": "string", "integer": "integer", "boolean": "boolean"}


def _frame(lang: str) -> dict:
    """The JSON Schema of one frame of the `accept` tool."""
    return {"type": "object", "additionalProperties": False, "required": ["path", "caption"],
            "properties": {"path": {"type": "string", "description": say(lang, "mcp.arg_frame_path")},
                           "caption": {"type": "string", "description": say(lang, "mcp.arg_frame_caption")}}}


def _property(lang: str, field: Field) -> dict:
    """The JSON Schema of one argument."""
    if field.kind == "strings":
        return {"type": "array", "items": {"type": "string"}, "description": field.description}
    if field.kind == "frames":
        return {"type": "array", "items": _frame(lang), "description": field.description}
    if field.kind == "mark":
        return {"type": "string", "enum": list(MARK_FLAGS), "description": field.description}
    return {"type": _JSON_TYPES[field.kind], "description": field.description}


def _schema(lang: str, fields: tuple[Field, ...]) -> dict:
    """The JSON Schema of the tool arguments."""
    schema = {"type": "object", "properties": {f.key: _property(lang, f) for f in fields}}
    required = [f.key for f in fields if f.required]
    if required:
        schema["required"] = required
    schema["additionalProperties"] = False
    return schema


def _pos(key: str, description: str, kind: str = "string") -> Field:
    return Field(key, kind, description, required=True)


def _opt(key: str, kind: str, description: str, required: bool = False) -> Field:
    return Field(key, kind, description, "--" + key.replace("_", "-"), required)


@cache
def build(lang: str) -> tuple[Tool, ...]:
    """All the tools, described in `lang`. The argv they build does not depend on the language."""
    d = partial(say, lang)

    def tool(name: str, description: str, prefix: tuple[str, ...], *fields: Field,
             check: Callable[[dict], None] | None = None) -> Tool:
        return Tool(name, description, _schema(lang, fields), partial(_build, lang, prefix, fields, check))

    return (
        tool("status", d("mcp.tool_status"), ("status", "--peek"),
             _opt("no_sync", "boolean", d("mcp.arg_no_sync")),
             _opt("since", "string", d("mcp.arg_status_since"))),
        tool("card_add", d("mcp.tool_card_add"), ("card", "add"),
             _pos("title", d("mcp.arg_title")),
             _opt("body", "string", d("mcp.arg_body")),
             _opt("source", "string", d("mcp.arg_source")),
             _opt("top", "boolean", d("mcp.arg_add_top"))),
        tool("card_move", d("mcp.tool_card_move"), ("card", "move"),
             _pos("id", d("mcp.arg_card_id")),
             _opt("top", "boolean", d("mcp.arg_top")),
             _opt("bottom", "boolean", d("mcp.arg_bottom")),
             _opt("before", "string", d("mcp.arg_before")),
             _opt("after", "string", d("mcp.arg_after")), check=partial(_one_place, lang)),
        tool("card_close", d("mcp.tool_card_close"), ("card", "close"),
             _pos("id", d("mcp.arg_card_id")),
             _opt("by", "string", d("mcp.arg_by"))),
        tool("card_return", d("mcp.tool_card_return"), ("card", "return"),
             _pos("id", d("mcp.arg_card_id")),
             _opt("note", "string", d("mcp.arg_return_note"), required=True)),
        tool("card_show", d("mcp.tool_card_show"), ("card", "show"),
             _pos("id", d("mcp.arg_card_id"))),
        tool("decision_list", d("mcp.tool_decision_list"), ("decision", "list"),
             _opt("all", "boolean", d("mcp.arg_all"))),
        tool("decision_ask", d("mcp.tool_decision_ask"), ("decision", "ask"),
             _opt("kind", "string", d("mcp.arg_kind"), required=True),
             _opt("question", "string", d("mcp.arg_question"), required=True),
             _opt("proposed", "string", d("mcp.arg_proposed"), required=True),
             Field("options", "strings", d("mcp.arg_options"), "--option"),
             _opt("reason", "string", d("mcp.arg_reason")),
             _opt("card", "string", d("mcp.arg_decision_card"))),
        tool("decision_answer", d("mcp.tool_decision_answer"), ("decision", "answer"),
             _pos("id", d("mcp.arg_decision_id")),
             _pos("answer", d("mcp.arg_answer")),
             _opt("note", "string", d("mcp.arg_note")),
             _opt("free", "boolean", d("mcp.arg_free"))),
        tool("run_start", d("mcp.tool_run_start"), ("run", "start"),
             _pos("card", d("mcp.arg_card_id")),
             _opt("step", "integer", d("mcp.arg_step")),
             _opt("contracts", "integer", d("mcp.arg_contracts"))),
        tool("run_progress", d("mcp.tool_run_progress"), ("run", "progress"),
             _pos("id", d("mcp.arg_run_id")),
             _opt("contracts_done", "integer", d("mcp.arg_contracts_done"), required=True)),
        tool("run_finish", d("mcp.tool_run_finish"), ("run", "finish"),
             _pos("id", d("mcp.arg_run_id")),
             _opt("result", "string", d("mcp.arg_run_result"), required=True),
             _opt("contracts_done", "integer", d("mcp.arg_contracts_done")),
             _opt("tokens", "integer", d("mcp.arg_tokens")),
             _opt("minutes", "integer", d("mcp.arg_minutes")),
             _opt("agents", "integer", d("mcp.arg_agents")),
             _opt("tool_errors", "integer", d("mcp.arg_tool_errors")),
             _opt("note", "string", d("mcp.arg_note"))),
        tool("accept", d("mcp.tool_accept"), ("accept",),
             _pos("card", d("mcp.arg_card_id")),
             _opt("level", "integer", d("mcp.arg_level"), required=True),
             _opt("result", "string", d("mcp.arg_accept_result", values=", ".join(ACCEPT_RESULTS)), required=True),
             _opt("evidence", "string", d("mcp.arg_evidence")),
             Field("frames", "frames", d("mcp.arg_frames")),
             Field("steps", "strings", d("mcp.arg_steps"), "--step"),
             _opt("report", "string", d("mcp.arg_report"))),
        tool("review_week", d("mcp.tool_review_week"), ("review", "week"),
             _opt("since", "string", d("mcp.arg_review_since"))),
        tool("review_mark", d("mcp.tool_review_mark"), ("review", "mark"),
             _pos("week", d("mcp.arg_week")),
             _pos("n", d("mcp.arg_n"), kind="integer"),
             Field("status", "mark", d("mcp.arg_mark_status"), required=True)),
        tool("doctor", d("mcp.tool_doctor"), ("doctor",)),
    )


@cache
def by_name_for(lang: str) -> dict[str, Tool]:
    """The tools of `build(lang)` by name."""
    return {tool.name: tool for tool in build(lang)}


TOOLS: tuple[Tool, ...] = build(i18n.DEFAULT)
by_name: dict[str, Tool] = by_name_for(i18n.DEFAULT)
