"""Snapshot of the project state: what waits for the owner, what runs, what changed."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from the_nod import i18n, vocab
from the_nod.files import write_text_atomic
from the_nod.store import Store

SCHEMA = 1  # version of the state.json contract for clients
DEFAULT_SINCE_DAYS = 7
_CLOSED = ("done", "returned")
_STEP_OK = "ok"
_ACCEPTED = vocab.SOLVED
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def _default_since(store: Store, now: str, host: str) -> str:
    seen = store.seen().get(host)
    if seen:
        return seen
    week_ago = datetime.fromisoformat(now) - timedelta(days=DEFAULT_SINCE_DAYS)
    return week_ago.strftime(_TIME_FORMAT)


def _acceptance(store: Store, card: str | None) -> dict | None:
    """The acceptance of a card for its verdict: what was checked and what confirms it."""
    acceptance = store.load_acceptance(card) if card else None
    if acceptance is None:
        return None
    return {"level": acceptance.level, "result": acceptance.result, "evidence": acceptance.evidence,
            "frames": [{"path": f.path, "caption": f.caption} for f in acceptance.frames],
            "steps": list(acceptance.steps), "report": acceptance.report}


def _waiting(store: Store, decisions, titles) -> list[dict]:
    open_ones = sorted((d for d in decisions if d.answer is None), key=lambda d: d.created)
    result = []
    for d in open_ones:
        item = {"id": d.id, "kind": d.kind, "card": d.card, "card_title": titles.get(d.card),
                "question": d.question, "proposed": d.proposed, "options": list(d.options),
                "reason": d.reason, "created": d.created}
        if d.kind == "verdict":
            item["acceptance"] = _acceptance(store, d.card)
        result.append(item)
    return result


def _running(runs, cards) -> list[dict]:
    """Cards in status `running` and their open run, if any."""
    open_runs = {}
    for run in sorted(runs, key=lambda r: r.started):
        if run.finished is None:
            open_runs[run.card] = run
    result = []
    for card in cards.values():
        if card.status != "running":
            continue
        run = open_runs.get(card.id)
        step = next((s for s in card.steps if run and s.n == run.step), None)
        result.append({
            "card": card.id, "card_title": card.title,
            "step": run.step if run else None, "step_title": step.title if step else None,
            "run": run.id if run else None, "started": run.started if run else None,
            "contracts_done": run.contracts_done if run else 0,
            "contracts_total": run.contracts_total if run else 0,
        })
    return sorted(result, key=lambda r: (r["started"] is None, r["started"] or "", r["card"]))


def _since_block(store: Store, since: str, runs, cards) -> dict:
    finished = [r for r in runs if r.finished and r.finished >= since]
    accepted = 0
    for card in cards:
        acceptance = store.load_acceptance(card.id)
        if acceptance and acceptance.created >= since and acceptance.result == _ACCEPTED:
            accepted += 1
    done = sorted((c for c in cards if c.status == "done" and c.closed_at and c.closed_at >= since),
                  key=lambda c: c.closed_at)
    return {
        "from": since, "runs": len(finished),
        "steps_done": sum(1 for r in finished if r.result == _STEP_OK),
        "accepted": accepted, "tokens": sum(r.tokens for r in finished),
        "cards_done": [{"id": c.id, "title": c.title, "closed_at": c.closed_at} for c in done],
    }


def _backlog(store: Store, cards: dict, top: int) -> dict:
    queue = [cards[i] for i in store.order() if i in cards and cards[i].status not in _CLOSED]
    return {
        "total": len(queue),
        "top": [
            {"id": c.id, "title": c.title, "status": c.status, "brief": c.brief,
             "steps_total": len(c.steps), "steps_done": sum(1 for s in c.steps if s.done)}
            for c in queue[:top]
        ],
    }


def _review(store: Store) -> dict | None:
    """The latest review by week: totals, suggestions and the file path."""
    reviews = store.reviews()
    if not reviews:
        return None
    r = reviews[-1]
    return {"week": r.week, "since": r.since, "until": r.until, "runs": r.runs, "steps_done": r.steps_done,
            "stops": r.stops, "accepted": r.accepted, "tokens": r.tokens, "minutes": r.minutes,
            "suggestions": [{"n": s.n, "text": s.text, "status": s.status} for s in r.suggestions],
            "path": f"reviews/{r.week}.md"}


def build(store: Store, *, now: str, host: str, since: str | None, fresh: bool,
          stale_since: str | None, top: int = 15) -> dict:
    """Builds the state snapshot; only reads files. `lang` is the language in use, for the pane."""
    since = since or _default_since(store, now, host)
    card_list = store.cards()
    cards = {c.id: c for c in card_list}
    runs = store.runs()
    return {
        "schema": SCHEMA, "generated_at": now, "host": host, "lang": i18n.current(),
        "fresh": fresh, "stale_since": stale_since,
        "waiting": _waiting(store, store.decisions(), {i: c.title for i, c in cards.items()}),
        "running": _running(runs, cards),
        "since": _since_block(store, since, runs, card_list),
        "backlog": _backlog(store, cards, top),
        "lock": store.lock(),
        "review": _review(store),
    }


def write(store: Store, state: dict) -> Path:
    """Writes `state.json` next to the rest of the state."""
    path = store.root / "state.json"
    write_text_atomic(path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    return path
