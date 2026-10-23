"""The planner of a driver pass: pure functions without disk and git.

It takes lists of model objects and returns an `Action`. It only reads the answers
to decisions: the driver never closes a decision itself.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from the_nod import vocab
from the_nod.model import Card, Decision, Run

BATCH = 3
STUCK_SECONDS = 2400
REASK_SECONDS = 86400
QUEUE_STATUSES = ("briefing", "waiting-owner", "ready", "running", "accepting", "waiting-verdict", "returned")

_CONSUMED = re.compile(rf"^\s*{re.escape(vocab.CONSUMED_MARK)}", re.MULTILINE)
_CARD_MADE = re.compile(rf"^\s*{re.escape(vocab.CARD_MARK)}", re.MULTILINE)
_BATCH_LINE = re.compile(r"^\s*-\s+(\S+)", re.MULTILINE)


@dataclass(frozen=True)
class Action:
    """One action of a pass.

    `kind` is "react", "stuck", "accept", "run", "brief", "rebrief",
    "next-batch", "pain" or "idle".
    """

    kind: str
    card: str | None = None
    step: int | None = None
    decision: str | None = None
    run: str | None = None


def consumed(d: Decision) -> bool:
    """The driver already applied the answer: a `Consumed:` line, or for `pain` also a `Card:` line."""
    return bool(_CONSUMED.search(d.body)) or (d.kind == "pain" and bool(_CARD_MADE.search(d.body)))


def _answered(d: Decision) -> bool:
    return d.answer is not None


def _ts(value: str | None) -> float:
    """An ISO time in epoch seconds; an unreadable value gives 0."""
    try:
        return datetime.fromisoformat(value).timestamp() if value else 0.0
    except (ValueError, TypeError):
        return 0.0


def _ordered(cards: list[Card], order: list[str]) -> list[Card]:
    """The cards in the `order` order; the ones it does not know follow, by id."""
    pos = {cid: i for i, cid in enumerate(order)}
    return sorted(cards, key=lambda c: (pos.get(c.id, len(pos)), c.id))


def all_proposed(forks: list[Decision]) -> bool:
    """Every fork not consumed yet got the proposed answer."""
    return all(d.answer == d.proposed for d in forks if not consumed(d))


def batch_cards(cards: list[Card], order: list[str], decisions: list[Decision] = ()) -> list[Card]:
    """The first `BATCH` backlog cards in order, without open decisions."""
    blocked = {d.card for d in decisions if not _answered(d) and d.card}
    return [c for c in _ordered(cards, order) if c.status == "backlog" and c.id not in blocked][:BATCH]


def _applies(d: Decision, by_id: dict[str, Card], decisions: list[Decision]) -> bool:
    card = by_id.get(d.card) if d.card else None
    if d.kind in ("return", "run-stuck"):
        return card is not None and card.status == "returned"
    if d.kind == "fork":
        open_forks = any(o.kind == "fork" and o.card == d.card and not _answered(o) for o in decisions)
        return card is not None and card.status == "waiting-owner" and not open_forks
    if d.kind == "next-batch":
        if d.answer != vocab.YES:
            return False
        ids = _BATCH_LINE.findall(d.body)
        return any(i in by_id and by_id[i].status == "backlog" for i in ids)
    if d.kind == "pain":
        return d.answer != d.proposed and not _CARD_MADE.search(d.body)
    if d.kind == "owner-action":
        return card is not None
    return False


def reactions(cards: list[Card], decisions: list[Decision]) -> list[Action]:
    """The answered decisions the driver has not applied yet, by `answered_at`."""
    by_id = {c.id: c for c in cards}
    pending = [d for d in decisions if _answered(d) and not consumed(d) and _applies(d, by_id, decisions)]
    pending.sort(key=lambda d: _ts(d.answered_at))
    return [Action("react", card=d.card, decision=d.id) for d in pending]


def _declined_recently(decisions: list[Decision], kind: str, declined: Callable[[Decision], bool], now: float) -> bool:
    """There is an open decision, or the last refusal is younger than `REASK_SECONDS`."""
    mine = [d for d in decisions if d.kind == kind]
    if any(not _answered(d) for d in mine):
        return True
    refusals = [_ts(d.answered_at) for d in mine if declined(d)]
    return bool(refusals) and now - max(refusals) < REASK_SECONDS


def next_action(
    cards: list[Card],
    decisions: list[Decision],
    runs: list[Run],
    order: list[str],
    now: str,
    *,
    run_mtime: Callable[[str], float],
    clock: float,
) -> Action:
    """The first fitting action of the pass; `react` never comes from here."""
    ordered = _ordered(cards, order)
    blocked = {d.card for d in decisions if not _answered(d) and d.card}
    by_id = {c.id: c for c in cards}

    open_runs = {r.card: r for r in runs if r.finished is None}
    for card in ordered:
        if card.status != "running":
            continue
        run = open_runs.get(card.id)
        if run is None:
            return Action("stuck", card=card.id, run=None)
        if clock - max(_ts(run.started), run_mtime(run.id)) > STUCK_SECONDS:
            return Action("stuck", card=card.id, run=run.id)

    for card in ordered:
        if card.status == "accepting" and card.id not in blocked:
            return Action("accept", card=card.id)

    # Only a running card holds the queue. An open run of a card in any other status is abandoned
    # (an old state: `nod card return` used to leave it open), and a pass does not wait for it.
    if not any(c.status == "running" for c in cards):
        for card in ordered:
            if card.status == "ready" and card.id not in blocked:
                step = next((s.n for s in card.steps if not s.done), None)
                return Action("run", card=card.id, step=step)

    for card in ordered:
        if card.status == "briefing" and card.id not in blocked:
            return Action("brief", card=card.id)
    for card in ordered:
        if card.status == "backlog" and card.source != "import" and card.id not in blocked:
            return Action("brief", card=card.id)

    if any(c.status in QUEUE_STATUSES for c in cards):
        return Action("idle")

    now_ts = _ts(now)
    backlog = [c for c in cards if c.status == "backlog"]
    if backlog:
        if _declined_recently(decisions, "next-batch", lambda d: d.answer == vocab.NO, now_ts):
            return Action("idle")
        return Action("next-batch")
    if _declined_recently(decisions, "pain", lambda d: d.answer == vocab.WAIT, now_ts):
        return Action("idle")
    return Action("pain")
