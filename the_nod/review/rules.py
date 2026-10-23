"""The rules of review suggestions: numbered suggestions from the numbers of a period."""

from dataclasses import replace

from the_nod.i18n import t
from the_nod.model import Suggestion
from the_nod.review.collect import NO_TITLE, Stats, median, paid_tokens
from the_nod.review.plural import pick

BRIEF_ATTEMPTS_MAX = 2
EXPENSIVE_FACTOR = 2
MIN_RUNS_FOR_MEDIAN = 2
OPEN_HOURS = 24
STOPS_MIN = 2
TOOL_ERRORS_MIN = 5
PERIOD_TARGET = "period"


def fmt_tokens(n: int) -> str:
    """Tokens short: `999`, `418 K`, `1.2 M` (`1,2 M` where the decimal mark is a comma)."""
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{round(n / 1000)} K"
    return f"{n / 1_000_000:.1f}".replace(".", t("review.decimal")) + " M"


def _titles(stats: Stats) -> dict[str, str]:
    """Card titles from all the rows of the period."""
    titles = {r.card: r.title for r in stats.run_rows} | {s.card: s.title for s in stats.spend_rows}
    return titles | {c.id: c.title for c in stats.cards}


def _card_order(stats: Stats, extra: list[str]) -> list[str]:
    """Cards in the order of `stats.cards`, then the missing ones from `extra`."""
    return list(dict.fromkeys([c.id for c in stats.cards] + extra))


def _brief_attempts(stats: Stats) -> list[tuple[str, str]]:
    """Cards whose brief was started more than twice."""
    titles = _titles(stats)
    found = []
    for card in _card_order(stats, list(stats.brief_attempts)):
        n = stats.brief_attempts.get(card, 0)
        if n > BRIEF_ATTEMPTS_MAX:
            attempts = pick(n, "review.attempt_one", "review.attempt_few", "review.attempt_many")
            found.append((card, t("review.s_brief_attempts", card=card, title=titles.get(card, NO_TITLE),
                                  count=n, attempts=attempts)))
    return found


def _expensive_run(stats: Stats) -> list[tuple[str, str]]:
    """Runs costing more than two period medians; the median counts the runs with tokens, two at least."""
    paid = paid_tokens(stats.run_rows)
    if len(paid) < MIN_RUNS_FOR_MEDIAN:
        return []
    middle = median(paid)
    if middle <= 0:
        return []
    return [(r.id, t("review.s_expensive_run", id=r.id, card=r.card, step=r.step if r.step is not None else NO_TITLE,
                     tokens=fmt_tokens(r.tokens), median=fmt_tokens(middle)))
            for r in stats.run_rows if r.tokens > EXPENSIVE_FACTOR * middle]


def _open_decision(stats: Stats) -> list[tuple[str, str]]:
    """Decisions without an answer for more than a day."""
    return [(d.id, t("review.s_open_decision", id=d.id, question=d.question, hours=d.hours))
            for d in stats.open_over_day if d.hours >= OPEN_HOURS]


def _stops(stats: Stats) -> list[tuple[str, str]]:
    """Cards with two or more stops in the period."""
    counts: dict[str, int] = {}
    for r in stats.run_rows:
        if r.result == "stop":
            counts[r.card] = counts.get(r.card, 0) + 1
    return [(card, t("review.s_stops", card=card, count=counts[card],
                     stops=pick(counts[card], "review.stop_one", "review.stop_few", "review.stop_many")))
            for card in _card_order(stats, list(counts)) if counts.get(card, 0) >= STOPS_MIN]


def _stuck(stats: Stats) -> list[tuple[str, str]]:
    """Runs that hung in the period."""
    if stats.stuck <= 0:
        return []
    return [(PERIOD_TARGET, t("review.s_stuck", count=stats.stuck))]


def _tool_errors(stats: Stats) -> list[tuple[str, str]]:
    """Runs with five or more tool errors."""
    return [(r.id, t("review.s_tool_errors", id=r.id, count=r.tool_errors, card=r.card))
            for r in stats.run_rows if r.tool_errors >= TOOL_ERRORS_MIN]


def _unverified(stats: Stats) -> list[tuple[str, str]]:
    """Acceptances with the result `unverified` in the period."""
    if stats.unverified <= 0:
        return []
    return [(PERIOD_TARGET, t("review.s_unverified", count=stats.unverified))]


RULES = (
    ("brief-attempts", _brief_attempts),
    ("expensive-run", _expensive_run),
    ("open-decision", _open_decision),
    ("stops", _stops),
    ("stuck", _stuck),
    ("tool-errors", _tool_errors),
    ("unverified", _unverified),
)


def suggest(stats: Stats) -> list[Suggestion]:
    """Suggestions by the rules in the order of `RULES`, numbered from 1."""
    found = [(rule, target, text) for rule, fn in RULES for target, text in fn(stats)]
    return [Suggestion(n, rule, target, text) for n, (rule, target, text) in enumerate(found, start=1)]


def merge_status(new: list[Suggestion], old: list[Suggestion]) -> list[Suggestion]:
    """New suggestions with the status of the old one that has the same rule and target."""
    statuses: dict[tuple[str, str], str] = {}
    for s in old:
        statuses.setdefault((s.rule, s.target), s.status)
    return [replace(s, status=statuses.get((s.rule, s.target), s.status)) for s in new]
