"""The driver reactions to the owner's answers, the next batch question and "what hurts".

Each reaction applies once: the decision gets a `Consumed:` line (a `pain` gets `Card:`),
and a decision already consumed is skipped without a write.
"""

import dataclasses
import re

from the_nod import harness as harness_mod
from the_nod import vocab
from the_nod.context import Context
from the_nod.driver import plan
from the_nod.driver.apply_brief import (append_line, brief, consumed, forget_cycle,
                                        fork_answers, load_card)
from the_nod.driver.log import Log
from the_nod.i18n import t
from the_nod.model import Card, Decision
from the_nod.transitions import make_decision

TITLE_LIMIT = 120
_BATCH_LINE = re.compile(r"^\s*-\s+(\S+)", re.MULTILINE)
# The card status at which a reaction still fits; `owner-action` fits any status.
EXPECTED_STATUS = {"fork": "waiting-owner", "return": "returned", "run-stuck": "returned"}


def _forks_to_apply(store, card_id: str) -> list[Decision]:
    return [d for d in store.decisions() if d.kind == "fork" and d.card == card_id
            and d.answer is not None and not plan.consumed(d)]


def _to_backlog(ctx: Context, card: Card, decision: Decision) -> None:
    """The card goes to the bottom of the backlog and the decision is consumed, in one commit."""
    store = ctx.store
    back = dataclasses.replace(card, status="backlog")
    marked = consumed(decision, ctx.now)

    def apply() -> None:
        store.save_card(back)
        store.set_order([*(x for x in store.order() if x != card.id), card.id])
        store.save_decision(marked)

    ctx.write(f"driver react {decision.id} backlog", apply)
    forget_cycle(store, card.id)


def _set_status(ctx: Context, card: Card, decisions: list[Decision], status: str) -> None:
    store = ctx.store
    moved = dataclasses.replace(card, status=status)
    marked = [consumed(d, ctx.now) for d in decisions]

    def apply() -> None:
        store.save_card(moved)
        for d in marked:
            store.save_decision(d)

    ctx.write(f"driver react {decisions[0].id} {status}", apply)


def _mark_only(ctx: Context, decision: Decision) -> None:
    marked = consumed(decision, ctx.now)
    ctx.write(f"driver react {decision.id}", lambda: ctx.store.save_decision(marked))


def _react_fork(ctx, get_harness, log, card: Card) -> bool | None:
    forks = _forks_to_apply(ctx.store, card.id)
    if not forks:
        return None
    if plan.all_proposed(forks):
        _set_status(ctx, card, forks, "ready")
        log.info(t("driver.forks_as_proposed", card=card.id))
        return None
    return brief(ctx, get_harness(), log, card.id, answers=fork_answers(forks), consume=tuple(forks))


def _react_card(ctx, get_harness, log, card: Card, d: Decision) -> bool | None:
    """The rebrief result (`True`/`False`) if the reaction started one; otherwise `None`."""
    if d.kind == "fork":
        return _react_fork(ctx, get_harness, log, card)
    if d.kind == "return" and d.answer == vocab.RERUN:
        # `reason` is the driver's text (why the card came back), `note` the owner's: two labels.
        notes = [*([t("driver.return_reason", reason=d.reason)] if d.reason else []),
                 *([t("driver.owner_note", note=d.note)] if d.note else [])]
        return brief(ctx, get_harness(), log, card.id, append=notes, consume=(d,))
    if d.kind == "run-stuck" and d.answer == vocab.RESTART:
        _set_status(ctx, card, [d], "ready")
    elif d.kind in ("return", "run-stuck", "owner-action") and d.answer in (vocab.BACKLOG, vocab.POSTPONE):
        _to_backlog(ctx, card, d)
    elif d.kind == "owner-action" and d.answer == vocab.DONE:
        _mark_only(ctx, d)
    else:
        log.warn(t("driver.answer_unknown", answer=d.answer, kind=d.kind, id=d.id))
        _mark_only(ctx, d)
    return None


def _react_batch(ctx: Context, log: Log, d: Decision) -> None:
    store = ctx.store
    if d.answer != vocab.YES:
        _mark_only(ctx, d)
        return
    ids = _batch_ids(d)
    cards = [dataclasses.replace(c, status="briefing") for c in store.cards()
             if c.id in ids and c.status == "backlog"]
    marked = consumed(d, ctx.now)

    def apply() -> None:
        for c in cards:
            store.save_card(c)
        store.save_decision(marked)

    ctx.write(f"driver react {d.id} next-batch", apply)
    log.info(t("driver.batch_started", cards=", ".join(c.id for c in cards)))


def _batch_ids(d: Decision) -> set[str]:
    """The ids from the body lines `- <id>  <title>` (the same parsing as `plan._BATCH_LINE`)."""
    return set(_BATCH_LINE.findall(d.body))


def _react_pain(ctx: Context, log: Log, d: Decision) -> None:
    store = ctx.store
    if d.answer == d.proposed:
        _mark_only(ctx, d)
        return
    answer = d.answer or ""
    title = (answer.strip().splitlines() or [""])[0].strip()[:TITLE_LIMIT]
    card = Card(id=store.new_id("c"), title=title, status="backlog", created=ctx.now,
                source="owner", body=answer)
    marked = dataclasses.replace(d, body=append_line(d.body, f"{vocab.CARD_MARK} {card.id}"))

    def apply() -> None:
        store.save_card(card)
        store.set_order([card.id, *(x for x in store.order() if x != card.id)])
        store.save_decision(marked)

    ctx.write(f"driver react {d.id} pain {card.id}", apply)
    log.info(t("driver.pain_card", card=card.id))


def react_with(ctx: Context, harness: harness_mod.Harness | None, log: Log,
               action: plan.Action) -> bool | None:
    """Applies one answered decision; `harness` is needed for a rebrief only.

    `None` means there was no rebrief; otherwise what `brief` returned: the agent command
    of this pass already ran (or failed before it), `True` means the brief is written.
    """
    store = ctx.store
    try:
        d = store.load_decision(action.decision)
    except (FileNotFoundError, ValueError) as err:
        log.error(t("driver.decision_unreadable", id=action.decision, error=err))
        return None
    if d.answer is None or plan.consumed(d):
        return None
    if d.kind == "next-batch":
        _react_batch(ctx, log, d)
        return None
    if d.kind == "pain":
        _react_pain(ctx, log, d)
        return None
    card = load_card(ctx, log, d.card) if d.card else None
    if card is None:
        return None
    expected = EXPECTED_STATUS.get(d.kind)
    if expected is not None and card.status != expected:
        log.info(t("driver.reaction_skipped", id=d.id, card=card.id, status=card.status))
        return None
    return _react_card(ctx, lambda: harness or harness_mod.load(store), log, card, d)


def react(ctx: Context, log: Log, action: plan.Action) -> bool | None:
    """The same as `react_with`; the manifest is read only when a rebrief needs it."""
    return react_with(ctx, None, log, action)


def ask_next_batch(ctx: Context, log: Log) -> str:
    """The next batch question; without candidates, `""` and nothing is written."""
    store = ctx.store
    cards = plan.batch_cards(store.cards(), store.order(), store.decisions())
    if not cards:
        return ""
    decision = make_decision(
        store, kind="next-batch", question=t("driver.batch_question", n=len(cards)),
        proposed=vocab.YES, options=[vocab.YES, vocab.NO], reason="; ".join(c.title for c in cards),
        body="\n".join(f"- {c.id}  {c.title}" for c in cards), now=ctx.now)
    ctx.write(f"driver next-batch {decision.id}", lambda: store.save_decision(decision))
    log.info(t("driver.asked_batch", id=decision.id))
    return decision.id


def ask_pain(ctx: Context, log: Log) -> str:
    decision = make_decision(ctx.store, kind="pain", question=t("driver.pain_question"),
                             proposed=vocab.WAIT, options=[vocab.WAIT], now=ctx.now)
    ctx.write(f"driver pain {decision.id}", lambda: ctx.store.save_decision(decision))
    log.info(t("driver.asked_pain", id=decision.id))
    return decision.id
