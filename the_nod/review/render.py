"""The weekly review as text: the file body, the summary line, the command output."""

import re
from datetime import datetime, timedelta

from the_nod import i18n, vocab
from the_nod.i18n import t
from the_nod.model import Review, Suggestion
from the_nod.review.collect import NO_TITLE, Stats
from the_nod.review.rules import fmt_tokens

DEFAULT_DAYS = 7
STOP_RESULT = "stop"
MARK_RE = re.compile(rf"^(\d+)\. \[({vocab.PROPOSED}|{vocab.APPLIED})\]", re.MULTILINE)
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def week_id(until: str) -> str:
    """The ISO week of the date `until` as `YYYY-WW`."""
    year, week, _ = datetime.fromisoformat(until).isocalendar()
    return f"{year}-{week:02d}"


def default_since(now: str) -> str:
    """The default period start: `now` minus seven days."""
    return (datetime.fromisoformat(now) - timedelta(days=DEFAULT_DAYS)).strftime(_TIME_FORMAT)


def _none() -> str:
    return t("review.none")


def _day(stamp: str) -> str:
    """A short date: `14 Oct`."""
    moment = datetime.fromisoformat(stamp)
    return f"{moment.day} {t('review.months').split()[moment.month - 1]}"


def _period(since: str, until: str) -> str:
    return f"{_day(since)} — {_day(until)}"


def _totals(item: Stats | Review) -> str:
    """The totals of the period in one line; both `Stats` and `Review` fit."""
    return t("review.totals", runs=item.runs, steps=item.steps_done, stops=item.stops, accepted=item.accepted,
             tokens=fmt_tokens(item.tokens), minutes=item.minutes, commits=item.commits)


def _cell(value) -> str:
    """A table cell: a vertical bar is escaped, a line break becomes a space."""
    return " ".join(str(value).split()).replace("|", "\\|")


def _table(head: tuple[str, ...], rows: list[tuple]) -> list[str]:
    if not rows:
        return [_none()]
    lines = [f"| {' | '.join(head)} |", f"|{'|'.join('---' for _ in head)}|"]
    return lines + [f"| {' | '.join(_cell(v) for v in row)} |" for row in rows]


def _suggestion_lines(suggestions: list[Suggestion]) -> list[str]:
    if not suggestions:
        return [t("review.no_suggestions")]
    return [f"{s.n}. [{s.status}] {s.text}" for s in suggestions]


def _cards(stats: Stats) -> list[str]:
    head = tuple(t("review.cols_cards").split("|"))
    return _table(head, [(c.id, c.title, c.briefs, c.runs, c.stops, c.accepts, fmt_tokens(c.tokens), c.status)
                         for c in stats.cards])


def _kinds(stats: Stats) -> list[str]:
    head = tuple(t("review.cols_kinds").split("|"))
    return _table(head, [(k.kind, k.calls, fmt_tokens(k.tokens), fmt_tokens(k.median), fmt_tokens(k.maximum),
                          k.minutes) for k in stats.kinds])


def _costly(stats: Stats) -> list[str]:
    head = tuple(t("review.cols_costly").split("|"))
    return _table(head, [(c.label, c.card, fmt_tokens(c.tokens), c.minutes, c.outcome) for c in stats.costly])


def _stop_text(stats: Stats) -> str:
    parts = []
    for r in stats.run_rows:
        if r.result != STOP_RESULT:
            continue
        step = r.step if r.step is not None else NO_TITLE
        parts.append(t("review.stop_entry", id=r.id, card=r.card, step=step) + (f": {r.note}" if r.note else ""))
    return "; ".join(parts) or _none()


def _failures(stats: Stats) -> list[str]:
    return [t("review.line_repeats", value=", ".join(stats.repeats) or _none()),
            t("review.line_stops", value=_stop_text(stats)),
            t("review.line_stuck", value=stats.stuck or _none()),
            t("review.line_failed_briefs", value=", ".join(stats.failed_briefs) or _none())]


def _answers(stats: Stats) -> list[str]:
    median = stats.median_answer_hours
    tail = t("review.answers_median", hours=median) if median is not None else t("review.answers_no_median")
    lines = [t("review.answers", asked=stats.asked, answered=stats.answered, tail=tail)]
    return lines + [t("review.open_decision", id=d.id, question=d.question, hours=d.hours, created=d.created)
                    for d in stats.open_over_day]


def body(stats: Stats, suggestions: list[Suggestion]) -> str:
    """The Markdown of a review: the title, the totals and the sections in a fixed order."""
    sections = [
        (t("review.h_improve"), _suggestion_lines(suggestions)),
        (t("review.h_cards"), _cards(stats)),
        (t("review.h_kinds"), _kinds(stats)),
        (t("review.h_costly"), _costly(stats)),
        (t("review.h_failures"), _failures(stats)),
        (t("review.h_answers"), _answers(stats)),
    ]
    totals = _totals(stats)
    lines = [t("review.title", week=week_id(stats.until), period=_period(stats.since, stats.until)), "",
             totals[0].upper() + totals[1:]]
    for head, rows in sections:
        lines += ["", head, "", *rows]
    return "\n".join(lines) + "\n"


def to_review(stats: Stats, suggestions: list[Suggestion], *, week: str, now: str) -> Review:
    """A review ready to write: the numbers of the period, the suggestions and the body."""
    return Review(
        week=week, since=stats.since, until=stats.until, generated_at=now, runs=stats.runs,
        steps_done=stats.steps_done, stops=stats.stops, stuck=stats.stuck, accepted=stats.accepted,
        unverified=stats.unverified, tokens=stats.tokens, minutes=stats.minutes, commits=stats.commits,
        asked=stats.asked, answered=stats.answered, open_over_day=len(stats.open_over_day),
        suggestions=list(suggestions), body=body(stats, suggestions))


def summary(review: Review, rel: str) -> str:
    """The text for stdout: the totals, the suggestions and the file path."""
    lines = [t("review.summary_title", week=review.week, period=_period(review.since, review.until),
               totals=_totals(review)), t("review.summary_improve")]
    lines += [f"  {s.n}. [{s.status}] {s.text}" for s in review.suggestions] or [f"  {_none()}"]
    return "\n".join(lines + [t("review.summary_written", path=rel)])


def _improve_heads() -> tuple[str, ...]:
    """The "what to improve" heading in every language: a review may be marked in another language than it was written in."""
    return tuple(i18n.catalog(lang)["review.h_improve"] for lang in i18n.LANGS)


def mark_body(text: str, n: int, status: str) -> str:
    """Swaps the status of the line `N. [status]` in the "what to improve" section; the rest of the body stays."""
    found = [(text.find(head), head) for head in _improve_heads() if head in text]
    if not found:
        return text
    start, head = min(found)
    end = text.find("\n## ", start + len(head))
    end = len(text) if end < 0 else end

    def swap(match: re.Match) -> str:
        return f"{n}. [{status}]" if int(match.group(1)) == n else match.group(0)

    return text[:start] + MARK_RE.sub(swap, text[start:end]) + text[end:]
