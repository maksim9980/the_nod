"""The spend of a command: tokens, minutes, subagents, tool errors.

The sources are the JSON of one `claude -p --output-format json` call and the transcripts
in `~/.claude/projects/<slug>/`.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

from the_nod.i18n import t

# `modelUsage` fields (summed over all agents, subagents included).
MODEL_TOKEN_FIELDS = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")
# `usage` fields: the parent agent only; the fallback.
USAGE_TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
AUTH_MARKERS = ("authenticate", "oauth")
ERROR_MARKERS = ('"is_error":true', '"is_error": true')


@dataclass(frozen=True)
class Usage:
    """The spend of one command."""

    tokens: int = 0
    minutes: int = 0
    agents: int = 0
    tool_errors: int = 0
    session: str | None = None
    cost_usd: float | None = None


def _result_object(stdout: str) -> dict | None:
    """The last stdout line that is a JSON object with `type == "result"`, else `None`."""
    for line in reversed(stdout.splitlines()):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "result":
            return obj
    return None


def _sum_fields(source: object, fields: tuple[str, ...]) -> int:
    if not isinstance(source, dict):
        return 0
    return sum(int(source.get(k) or 0) for k in fields)


def _tokens(obj: dict) -> int:
    """Tokens by `modelUsage`; without it, by `usage`."""
    model_usage = obj.get("modelUsage")
    if isinstance(model_usage, dict) and model_usage:
        return sum(_sum_fields(m, MODEL_TOKEN_FIELDS) for m in model_usage.values())
    return _sum_fields(obj.get("usage"), USAGE_TOKEN_FIELDS)


def from_claude_json(stdout: str) -> Usage | None:
    """The spend from the `claude -p` JSON; `None` if the output has no result."""
    obj = _result_object(stdout)
    if obj is None:
        return None
    cost = obj.get("total_cost_usd")
    return Usage(
        tokens=_tokens(obj),
        minutes=round(int(obj.get("duration_ms") or 0) / 60000),
        session=obj.get("session_id"),
        cost_usd=float(cost) if cost is not None else None,
    )


def _flag(value: object) -> str:
    return "—" if value is None else str(value).lower() if isinstance(value, bool) else str(value)


def claude_summary(stdout: str) -> str:
    """The `claude -p` result in one line: why the agent stopped; empty without the result JSON."""
    obj = _result_object(stdout)
    if obj is None:
        return ""
    cost = obj.get("total_cost_usd")
    money = f"{cost:.2f}" if isinstance(cost, (int, float)) else "—"
    return t("driver.claude_line", subtype=_flag(obj.get("subtype")), is_error=_flag(obj.get("is_error")),
             reason=_flag(obj.get("terminal_reason")), turns=_flag(obj.get("num_turns")), cost=money)


def auth_failure(stdout: str) -> str | None:
    """The `result` text when the login failed: `is_error` is true and the text has "authenticate" or "OAuth"."""
    obj = _result_object(stdout)
    if obj is None or not obj.get("is_error"):
        return None
    text = obj.get("result")
    if isinstance(text, str) and any(m in text.lower() for m in AUTH_MARKERS):
        return text
    return None


def project_slug(root: Path) -> str:
    """The transcript folder name: every character outside `[A-Za-z0-9]` becomes "-"."""
    return re.sub(r"[^A-Za-z0-9]", "-", os.fspath(root))


def transcript_dir(root: Path) -> Path:
    return Path.home() / ".claude" / "projects" / project_slug(root)


def count_agents(root: Path, session: str) -> int:
    """The number of subagent files of the session; 0 without the folder."""
    sub = transcript_dir(root) / session / "subagents"
    return sum(1 for _ in sub.glob("agent-*.jsonl")) if sub.is_dir() else 0


def count_tool_errors(root: Path, session: str) -> int:
    """The number of transcript lines with `is_error: true`; 0 without the file."""
    path = transcript_dir(root) / f"{session}.jsonl"
    if not path.is_file():
        return 0
    with path.open(encoding="utf-8", errors="replace") as fh:
        return sum(1 for line in fh if any(m in line for m in ERROR_MARKERS))


def measure(stdout: str, root: Path) -> Usage:
    """The spend from the JSON plus the transcript counters; `Usage()` without the JSON or with non-numeric fields."""
    try:
        base = from_claude_json(stdout)
    except (TypeError, ValueError, AttributeError):
        return Usage()
    if base is None:
        return Usage()
    sid = base.session
    if not sid:
        return base
    return replace(base, agents=count_agents(root, sid), tool_errors=count_tool_errors(root, sid))
