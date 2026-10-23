"""The numbers of a review period: runs, acceptances, decisions and agent spend, from the objects of the store."""

import re
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from the_nod import i18n, vocab
from the_nod.i18n import t
from the_nod.model import Acceptance, Card, Decision, Run, Spend
from the_nod.review import plural
from the_nod.store import ID_RE, Store

BRIEF_START = re.compile(r"^state: driver brief (\S+) briefing$")
STUCK_KIND = "run-stuck"
DAY_HOURS = 24
NO_TITLE = "—"
COSTLY_TOP = 5
KIND_ORDER = ("brief", "run", "accept")


def failed_brief_prefixes() -> tuple[str, ...]:
    """The fixed start of the driver's failed-brief note (`driver.brief_failed_note`) in every language.

    The driver writes the note in the project language of the moment, so a state may hold both.
    """
    return tuple(i18n.catalog(lang)["driver.brief_failed_note"].split("{", 1)[0] for lang in i18n.LANGS)


def _failed_brief(d) -> bool:
    """The driver writes the failed-brief text into `reason`; a state from before that kept it in `note`."""
    prefixes = failed_brief_prefixes()
    return d.reason.startswith(prefixes) or d.note.startswith(prefixes)


@dataclass(frozen=True)
class RunRow:
    """A run of the period; `note` is the first line of the run body, or an empty string."""

    id: str
    card: str
    title: str
    step: int | None
    tokens: int
    minutes: int
    tool_errors: int
    result: str
    note: str


@dataclass(frozen=True)
class SpendRow:
    """A spend record of a brief or an acceptance in the period."""

    kind: str
    card: str
    title: str
    at: str
    tokens: int
    minutes: int


@dataclass(frozen=True)
class CardStat:
    """The totals of the period for one card."""

    id: str
    title: str
    briefs: int
    runs: int
    stops: int
    accepts: int
    tokens: int
    minutes: int
    status: str


@dataclass(frozen=True)
class KindStat:
    """The spend of one kind of agent command: brief, run or acceptance."""

    kind: str
    calls: int
    tokens: int
    median: int
    maximum: int
    minutes: int


@dataclass(frozen=True)
class OpenDecision:
    """A decision without an answer older than a day; `hours` run from its creation to the end of the period."""

    id: str
    question: str
    created: str
    hours: int


@dataclass(frozen=True)
class Costly:
    """A row of the most expensive calls: a run or a spend record."""

    label: str
    card: str
    title: str
    tokens: int
    minutes: int
    outcome: str


@dataclass(frozen=True)
class Stats:
    """All the numbers of a review for the period `[since, until)`."""

    since: str
    until: str
    runs: int
    steps_done: int
    stops: int
    stuck: int
    repeats: list[str]
    accepted: int
    unverified: int
    tokens: int
    minutes: int
    commits: int
    asked: int
    answered: int
    median_answer_hours: int | None
    open_over_day: list[OpenDecision]
    cards: list[CardStat]
    kinds: list[KindStat]
    run_rows: list[RunRow]
    spend_rows: list[SpendRow]
    costly: list[Costly]
    failed_briefs: list[str]
    brief_attempts: dict[str, int]


def _parse(stamp: str | None) -> datetime | None:
    """An ISO timestamp, or `None` when there is none or it does not read."""
    try:
        return datetime.fromisoformat(stamp) if stamp else None
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class _Period:
    """The half-open interval `[since, until)`."""

    since: datetime
    until: datetime

    def has(self, stamp: str | None) -> bool:
        """The timestamp lies in the period; an unreadable one lies outside it."""
        moment = _parse(stamp)
        return moment is not None and self.since <= moment < self.until


def median(values: list[int]) -> int:
    """The integer median; 0 for an empty list."""
    return round(statistics.median(values)) if values else 0


def _first_line(text: str) -> str:
    """The first non-empty line of the text, or an empty string."""
    lines = text.strip().splitlines()
    return lines[0].strip() if lines else ""


def _run_rows(runs: list[Run], titles: dict[str, str]) -> list[RunRow]:
    """Rows of the runs of the period, in store order."""
    return [RunRow(r.id, r.card, titles.get(r.card, NO_TITLE), r.step, r.tokens, r.minutes, r.tool_errors,
                   r.result or "", _first_line(r.body)) for r in runs]


def _spend_rows(spends: list[Spend], titles: dict[str, str]) -> list[SpendRow]:
    """Rows of the spend records of the period, in store order."""
    return [SpendRow(s.kind, s.card, titles.get(s.card, NO_TITLE), s.at, s.tokens, s.minutes) for s in spends]


def _repeats(runs: list[Run]) -> list[str]:
    """The pairs card-step with two or more runs in the period."""
    counts = Counter((r.card, r.step) for r in runs if r.step is not None)
    return [t("review.repeat_entry", card=card, step=step, count=k,
              times=plural.pick(k, "review.time_one", "review.time_few", "review.time_many"))
            for (card, step), k in counts.items() if k >= 2]


def _brief_attempts(subjects: list[str], spends: list[Spend]) -> dict[str, int]:
    """Brief attempts by commit subjects; without subjects, by the `brief` spend records."""
    if subjects:
        matches = (BRIEF_START.match(subject) for subject in subjects)
        return dict(Counter(match.group(1) for match in matches if match))
    return dict(Counter(s.card for s in spends if s.kind == "brief"))


def paid_tokens(rows: list) -> list[int]:
    """Tokens of the rows that spent more than zero: an unfinished run is not paid yet."""
    return [row.tokens for row in rows if row.tokens > 0]


def _kind_stat(kind: str, rows: list) -> KindStat:
    """The summary of the calls of one kind; the median and maximum of runs count the runs with tokens only."""
    tokens = [row.tokens for row in rows]
    priced = paid_tokens(rows) if kind == "run" else tokens
    return KindStat(kind, len(rows), sum(tokens), median(priced), max(priced, default=0),
                    sum(row.minutes for row in rows))


def _kinds(run_rows: list[RunRow], spend_rows: list[SpendRow]) -> list[KindStat]:
    """Three rows of spend by kind: brief, run, acceptance."""
    by_kind = {"run": run_rows} | {k: [s for s in spend_rows if s.kind == k] for k in ("brief", "accept")}
    return [_kind_stat(kind, by_kind[kind]) for kind in KIND_ORDER]


def _costly(run_rows: list[RunRow], spend_rows: list[SpendRow]) -> list[Costly]:
    """The five most expensive calls of the period by tokens."""
    rows = [Costly(t("review.run_label", id=r.id, step=r.step) if r.step is not None else r.id, r.card, r.title,
                   r.tokens, r.minutes, r.result or t("review.running")) for r in run_rows]
    rows += [Costly(f"{s.kind} {s.card}", s.card, s.title, s.tokens, s.minutes, NO_TITLE) for s in spend_rows]
    return sorted(rows, key=lambda row: -row.tokens)[:COSTLY_TOP]


def _open_over_day(decisions: list[Decision], until: datetime) -> list[OpenDecision]:
    """Decisions without an answer, created more than a day before the end of the period."""
    edge = until - timedelta(hours=DAY_HOURS)
    found = []
    for d in decisions:
        created = _parse(d.created)
        if d.answer is None and created is not None and created < edge:
            hours = int((until - created).total_seconds() // 3600)
            found.append(OpenDecision(d.id, d.question, d.created, hours))
    return found


def _answer_hours(decisions: list[Decision]) -> int | None:
    """The median of hours from creation to answer; `None` when nothing was answered."""
    hours = []
    for d in decisions:
        created, answered = _parse(d.created), _parse(d.answered_at)
        if created is not None and answered is not None:
            hours.append((answered - created).total_seconds() / 3600)
    return round(statistics.median(hours)) if hours else None


def _acceptances(store: Store, ids: list[str], period: _Period) -> list[Acceptance]:
    """Acceptances of the known cards created in the period."""
    found = (store.load_acceptance(id) for id in ids if ID_RE.fullmatch(id))
    return [a for a in found if a is not None and period.has(a.created)]


def _card_stats(ids: list[str], cards: dict[str, Card], run_rows: list[RunRow], spend_rows: list[SpendRow],
                accepts: list[Acceptance], attempts: dict[str, int]) -> list[CardStat]:
    """Totals per card of the period, most tokens first."""
    stats = []
    for id in ids:
        runs = [r for r in run_rows if r.card == id]
        spends = [s for s in spend_rows if s.card == id]
        card = cards.get(id)
        stats.append(CardStat(
            id, card.title if card else NO_TITLE, attempts.get(id, 0), len(runs),
            sum(r.result == "stop" for r in runs), sum(a.card == id for a in accepts),
            sum(r.tokens for r in runs) + sum(s.tokens for s in spends),
            sum(r.minutes for r in runs) + sum(s.minutes for s in spends), card.status if card else NO_TITLE))
    return sorted(stats, key=lambda stat: -stat.tokens)


def _ordered_ids(*groups) -> list[str]:
    """Card ids without repeats, in order of first appearance."""
    return list(dict.fromkeys(id for group in groups for id in group if id))


def collect(store: Store, *, since: str, until: str, subjects: list[str]) -> Stats:
    """The numbers of the period `[since, until)` from the store and the commit subjects `subjects`."""
    start, end = _parse(since), _parse(until)
    if start is None or end is None:
        raise ValueError(t("review.bad_period", since=since, until=until))
    period = _Period(start, end)
    cards = {c.id: c for c in store.cards()}
    titles = {id: c.title for id, c in cards.items()}
    all_decisions = store.decisions()
    runs = [r for r in store.runs() if period.has(r.finished if r.finished else r.started)]
    spends = [s for s in store.spends() if period.has(s.at)]
    asked = [d for d in all_decisions if period.has(d.created)]
    answered = [d for d in all_decisions if period.has(d.answered_at)]
    accepts = _acceptances(store, _ordered_ids(cards, [r.card for r in runs], [s.card for s in spends]), period)
    run_rows, spend_rows = _run_rows(runs, titles), _spend_rows(spends, titles)
    attempts = _brief_attempts(subjects, spends)
    ids = _ordered_ids([r.card for r in runs], [s.card for s in spends], [a.card for a in accepts],
                       [d.card for d in asked + answered])
    return Stats(
        since=since, until=until, runs=len(runs), steps_done=sum(r.result == "ok" for r in runs),
        stops=sum(r.result == "stop" for r in runs), stuck=sum(d.kind == STUCK_KIND for d in asked),
        repeats=_repeats(runs), accepted=sum(a.result == vocab.SOLVED for a in accepts),
        unverified=sum(a.result == vocab.UNVERIFIED for a in accepts),
        tokens=sum(r.tokens for r in runs) + sum(s.tokens for s in spends),
        minutes=sum(r.minutes for r in runs) + sum(s.minutes for s in spends),
        commits=len(subjects), asked=len(asked), answered=len(answered),
        median_answer_hours=_answer_hours(answered), open_over_day=_open_over_day(all_decisions, period.until),
        cards=_card_stats(ids, cards, run_rows, spend_rows, accepts, attempts),
        kinds=_kinds(run_rows, spend_rows), run_rows=run_rows, spend_rows=spend_rows,
        costly=_costly(run_rows, spend_rows),
        failed_briefs=_ordered_ids([d.card for d in asked if d.kind == "return" and _failed_brief(d)]),
        brief_attempts=attempts,
    )
