"""The state model: card, step, decision, run, acceptance.

The classes turn into frontmatter metadata (`to_meta`) and back (`from_meta`).
The document body (`body`) does not go into the metadata.
"""

from dataclasses import MISSING, dataclass, field, fields
from datetime import datetime

from the_nod import vocab
from the_nod.i18n import t

CARD_STATUSES = (
    "backlog", "briefing", "waiting-owner", "ready", "running",
    "accepting", "waiting-verdict", "done", "returned",
)
DECISION_KINDS = ("brief-yes", "fork", "verdict", "next-batch", "return", "run-stuck", "pain", "owner-action")
ACCEPT_RESULTS = (vocab.SOLVED, vocab.UNSOLVED, vocab.UNVERIFIED)
CARD_SOURCES = ("owner", "agent", "import")
ACCEPT_LEVELS = (1, 2, 3)
SPEND_KINDS = ("brief", "accept")
SUGGESTION_STATUSES = (vocab.PROPOSED, vocab.APPLIED)


class ModelError(ValueError):
    """An invalid value or a missing field in the metadata."""


def now_iso() -> str:
    """Local time without a zone, for example `2026-10-20T14:02:00`."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _to_value(value):
    if isinstance(value, list):
        return [_to_value(item) for item in value]
    return value.to_meta() if isinstance(value, _Meta) else value


class _Meta:
    """The shared `to_meta` / `from_meta` logic of all model classes."""

    _checks: dict = {}  # field -> allowed values
    _nested: dict = {}  # field -> class of the list items

    def to_meta(self) -> dict:
        return {
            f.name: _to_value(getattr(self, f.name))
            for f in fields(self)
            if f.name != "body" and getattr(self, f.name) is not None
        }

    @classmethod
    def _nested_items(cls, name: str, value) -> list:
        if not isinstance(value, list) or not all(isinstance(i, dict) for i in value):
            raise ModelError(t("model.not_tables", field=name))
        return [cls._nested[name].from_meta(item) for item in value]

    @classmethod
    def from_meta(cls, meta: dict, body: str = ""):
        kwargs = {}
        for f in fields(cls):
            if f.name == "body":
                continue
            if f.name not in meta:
                if f.default is MISSING and f.default_factory is MISSING:
                    raise ModelError(t("model.missing_field", field=f.name))
                continue
            value = meta[f.name]
            allowed = cls._checks.get(f.name)
            if allowed is not None and value not in allowed:
                raise ModelError(t("model.bad_value", field=f.name, value=value))
            if f.name in cls._nested:
                value = cls._nested_items(f.name, value)
            kwargs[f.name] = value
        if "body" in {f.name for f in fields(cls)}:
            kwargs["body"] = body
        return cls(**kwargs)


@dataclass
class Step(_Meta):
    n: int
    title: str
    done: bool = False


@dataclass
class Card(_Meta):
    id: str
    title: str
    status: str
    created: str
    source: str
    brief: str | None = None
    steps: list[Step] = field(default_factory=list)
    closed_at: str | None = None
    closed_by: str | None = None
    body: str = ""
    _checks = {"status": CARD_STATUSES, "source": CARD_SOURCES}
    _nested = {"steps": Step}


@dataclass
class Decision(_Meta):
    id: str
    kind: str
    created: str
    question: str
    proposed: str
    options: list[str]
    reason: str = ""
    card: str | None = None
    answer: str | None = None
    answered_at: str | None = None
    answered_by: str | None = None
    note: str = ""
    body: str = ""
    _checks = {"kind": DECISION_KINDS}


@dataclass
class Run(_Meta):
    id: str
    card: str
    started: str
    step: int | None = None
    finished: str | None = None
    contracts_total: int = 0
    contracts_done: int = 0
    tokens: int = 0
    minutes: int = 0
    agents: int = 0
    tool_errors: int = 0
    result: str | None = None
    body: str = ""


@dataclass
class Frame(_Meta):
    path: str
    caption: str


@dataclass
class Acceptance(_Meta):
    card: str
    level: int
    result: str
    created: str
    evidence: str = ""
    frames: list[Frame] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    report: str | None = None
    body: str = ""
    _checks = {"level": ACCEPT_LEVELS, "result": ACCEPT_RESULTS}
    _nested = {"frames": Frame}


@dataclass
class Spend(_Meta):
    """Usage of one driver agent command (brief or acceptance); a run keeps its usage in the run itself."""

    kind: str
    card: str
    at: str
    tokens: int = 0
    minutes: int = 0
    agents: int = 0
    tool_errors: int = 0
    cost_usd: float | None = None
    body: str = ""
    _checks = {"kind": SPEND_KINDS}


@dataclass
class Suggestion(_Meta):
    """A numbered review suggestion: rule, target, text and status."""

    n: int
    rule: str
    target: str
    text: str
    status: str = vocab.PROPOSED
    _checks = {"status": SUGGESTION_STATUSES}


@dataclass
class Review(_Meta):
    """A weekly review: the numbers of the period and the suggestions."""

    week: str
    since: str
    until: str
    generated_at: str
    runs: int = 0
    steps_done: int = 0
    stops: int = 0
    stuck: int = 0
    accepted: int = 0
    unverified: int = 0
    tokens: int = 0
    minutes: int = 0
    commits: int = 0
    asked: int = 0
    answered: int = 0
    open_over_day: int = 0
    suggestions: list[Suggestion] = field(default_factory=list)
    body: str = ""
    _nested = {"suggestions": Suggestion}
