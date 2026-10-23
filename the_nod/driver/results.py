"""Result files: the TOML the agent command writes to the `{result}` path."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from the_nod import vocab
from the_nod.i18n import t
from the_nod.model import ACCEPT_LEVELS, ACCEPT_RESULTS
from the_nod.transitions import RESULTS


class ResultError(ValueError):
    """The result file is missing or breaks the contract. The text is `<path>: <reason>`."""

    def __init__(self, path, reason: str):
        self.path = path
        super().__init__(f"{path}: {reason}")


@dataclass(frozen=True)
class BriefResult:
    brief: str
    note: str = ""
    blocked: str = ""


@dataclass(frozen=True)
class RunResult:
    result: str
    contracts_total: int = 0
    contracts_done: int = 0
    note: str = ""
    blocked: str = ""


@dataclass(frozen=True)
class AcceptResult:
    level: int
    result: str
    evidence: str = ""
    frames: list[tuple[str, str]] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    report: str | None = None
    blocked: str = ""


def _load(path) -> dict:
    p = Path(path)
    if not p.is_file():
        raise ResultError(path, t("driver.result_missing"))
    try:
        return tomllib.loads(p.read_text(encoding="utf-8-sig"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as err:
        raise ResultError(path, f"TOML: {err}") from err


def _blocked(path, data: dict) -> str:
    value = data.get("blocked", "")
    if not isinstance(value, str):
        raise ResultError(path, t("model.bad_value", field="blocked", value=value))
    return value


def _get(path, data: dict, name: str, kind: type, default, required: bool):
    """The field value of the right type; a missing field gives `default`, or an error when it is required."""
    if name not in data:
        if required:
            raise ResultError(path, t("driver.result_no_field", field=name))
        return default
    value = data[name]
    if isinstance(value, bool) or not isinstance(value, kind):
        raise ResultError(path, t("model.bad_value", field=name, value=value))
    return value


def _choice(path, data: dict, name: str, allowed: tuple, default, required: bool):
    if name not in data:
        if required:
            raise ResultError(path, t("driver.result_no_field", field=name))
        return default
    value = data[name]
    if (name == "level" and type(value) is not int) or value not in allowed:
        raise ResultError(path, t("model.bad_value", field=name, value=data[name]))
    return data[name]


def _strings(path, data: dict, name: str) -> list[str]:
    value = data.get(name, [])
    if not isinstance(value, list) or not all(isinstance(i, str) for i in value):
        raise ResultError(path, t("driver.result_not_strings", field=name))
    return list(value)


def _frames(path, data: dict) -> list[tuple[str, str]]:
    value = data.get("frames", [])
    if not isinstance(value, list) or not all(isinstance(i, dict) for i in value):
        raise ResultError(path, t("model.not_tables", field="frames"))
    frames = []
    for item in value:
        frame_path = _get(path, item, "path", str, "", True)
        frames.append((frame_path, _get(path, item, "caption", str, "", False)))
    return frames


def read_brief(path) -> BriefResult:
    data = _load(path)
    blocked = _blocked(path, data)
    if blocked:
        return BriefResult("", blocked=blocked)
    return BriefResult(
        _get(path, data, "brief", str, "", True),
        _get(path, data, "note", str, "", False),
    )


def read_run(path) -> RunResult:
    data = _load(path)
    blocked = _blocked(path, data)
    if blocked:
        return RunResult("stop", blocked=blocked)
    return RunResult(
        _choice(path, data, "result", RESULTS, "stop", True),
        _get(path, data, "contracts_total", int, 0, False),
        _get(path, data, "contracts_done", int, 0, False),
        _get(path, data, "note", str, "", False),
    )


def read_accept(path) -> AcceptResult:
    data = _load(path)
    blocked = _blocked(path, data)
    if blocked:
        return AcceptResult(1, vocab.UNVERIFIED, blocked=blocked)
    report = data.get("report")
    if report is not None and not isinstance(report, str):
        raise ResultError(path, t("model.bad_value", field="report", value=report))
    return AcceptResult(
        _choice(path, data, "level", ACCEPT_LEVELS, 1, True),
        _choice(path, data, "result", ACCEPT_RESULTS, vocab.UNVERIFIED, True),
        _get(path, data, "evidence", str, "", False),
        _frames(path, data),
        _strings(path, data, "steps"),
        report,
    )
