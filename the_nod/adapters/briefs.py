"""The core brief format: ten `## N.` sections, forks in section 4, steps in section 10.

Shared by every adapter. The functions take text and read nothing from disk.
Labels come in both languages (decision R5): each one is an `(English, Russian)` pair, and a brief
may mix them. Sections are found by number, so their titles may be in any language.
"""
import re
from dataclasses import dataclass

from the_nod.i18n import t

DATE = r"\d{4}-\d{2}-\d{2}"
DATE_LABEL = ("Date:", "Дата:")
STATUS_LABEL = ("Status:", "Статус:")
FORK = ("Question:", "Вопрос:")
PROPOSED = ("Proposed:", "Предлагаю:")
REASON = ("Why:", "Почему:")
OPTIONS = ("Options:", "Варианты:")
OUTSIDE = ("Outside the run:", "Вне рана:")
OPTION_SEPARATOR = " | "
DECISIONS_SECTION, CHECK_SECTION, STEPS_SECTION = 4, 9, 10

# Each fork field label, in either language, maps to its pair: the pair names the field.
_FIELDS = {label: pair for pair in (PROPOSED, REASON, OPTIONS) for label in pair}


def _any(labels: tuple[str, ...]) -> str:
    """A regex group matching any of `labels` literally."""
    return "(?:" + "|".join(re.escape(label) for label in labels) + ")"


_STATUS = re.compile(rf"^{_any(DATE_LABEL)} [^\n]*?{_any(STATUS_LABEL)} ([^\s.]+)(?: ({DATE}))?", re.MULTILINE)
_DATE = re.compile(rf"{_any(DATE_LABEL)} ({DATE})")
_OUTSIDE = re.compile(rf"^{_any(OUTSIDE)} (.+)$", re.MULTILINE)
_TITLE = re.compile(r"^# (.+)$", re.MULTILINE)
_FORK = re.compile(rf"^{_any(FORK)}")
_NUMBERED = re.compile(r"^\d+\. (.*)")
_NUMBER_PREFIX = re.compile(r"^\d+\.\s*")
_MARKERS = re.compile(rf"(?:^|\s)({'|'.join(re.escape(label) for label in _FIELDS)})")


@dataclass(frozen=True)
class Brief:
    title: str
    date: str
    status: str
    status_date: str | None
    decisions: list[str]
    check: str
    steps: list[str]
    outside: str | None


@dataclass(frozen=True)
class Fork:
    question: str
    proposed: str
    reason: str
    options: list[str]


def _h2_blocks(text: str) -> list[tuple[int, str, list[str]]]:
    """Splits the text on `## ` lines: (line number, heading, body lines)."""
    blocks: list[tuple[int, str, list[str]]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            blocks.append((number, line[3:].strip(), []))
        elif blocks:
            blocks[-1][2].append(line)
    return blocks


def _section(text: str, number: int) -> list[str]:
    """The lines of section `## N.`; empty without the section."""
    for _, heading, body in _h2_blocks(text):
        if heading.startswith(f"{number}."):
            return body
    return []


def _numbered(lines: list[str]) -> list[str]:
    return [m.group(1).strip() for line in lines if (m := _NUMBERED.match(line))]


def _first(pattern: re.Pattern, text: str) -> str | None:
    """The first group of the first match, stripped; `None` without a match."""
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def parse_brief(text: str) -> Brief:
    status = _STATUS.search(text)
    if not status:
        raise ValueError(t("briefs.no_status"))
    title = _first(_TITLE, text)
    if title is None:
        raise ValueError(t("briefs.no_title"))
    date = _first(_DATE, text)
    if date is None:
        raise ValueError(t("briefs.no_date"))
    outside = _OUTSIDE.search(text)
    return Brief(
        title=title,
        date=date,
        status=status.group(1),
        status_date=status.group(2),
        decisions=_numbered(_section(text, DECISIONS_SECTION)),
        check="\n".join(_section(text, CHECK_SECTION)).strip(),
        steps=[step for step in _numbered(_section(text, STEPS_SECTION)) if step],
        outside=outside.group(1).strip() if outside else None,
    )


def _field(value: str) -> str:
    return value.strip().rstrip(".").strip()


def _parse_fork(line: str) -> Fork:
    body = _FORK.sub("", _NUMBER_PREFIX.sub("", line.strip()), count=1)
    parts = _MARKERS.split(body)
    fields = {_FIELDS[parts[i]]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}
    proposed = _field(fields.get(PROPOSED, ""))
    if not proposed:
        raise ValueError(t("briefs.fork_without_proposed", line=line))
    listed = [_field(o) for o in fields.get(OPTIONS, "").split(OPTION_SEPARATOR)]
    options = [proposed, *(o for o in listed if o and o != proposed)]
    return Fork(question=_field(parts[0]), proposed=proposed, reason=_field(fields.get(REASON, "")),
                options=options)


def parse_forks(decisions: list[str]) -> list[Fork]:
    """Section 4 lines that start with a `FORK` label: the forks for the owner."""
    return [_parse_fork(d) for d in decisions if _FORK.match(_NUMBER_PREFIX.sub("", d.strip()))]


def require_steps(brief: Brief) -> list[str]:
    if not brief.steps:
        raise ValueError(t("briefs.no_steps"))
    return brief.steps
