"""`nod decision`: questions to the owner and the answers — list, ask, answer."""

import json

from the_nod import context, transitions, vocab
from the_nod.commands.card import load_card, make_return_decision
from the_nod.i18n import t
from the_nod.model import DECISION_KINDS, Decision

# The one kind the driver's agent may ask: the other kinds are the driver's own questions.
AGENT_KIND = "owner-action"


def add_parser(sub) -> None:
    decision = sub.add_parser("decision", help=t("help.decision"))
    actions = decision.add_subparsers(dest="action", required=True)

    ls = actions.add_parser("list", help=t("help.decision_list"))
    ls.add_argument("--all", action="store_true", help=t("help.decision_all"))
    ls.set_defaults(run=_list)

    ask = actions.add_parser("ask", help=t("help.decision_ask"))
    ask.add_argument("--kind", required=True, help=t("help.decision_kind", kinds=", ".join(DECISION_KINDS)))
    ask.add_argument("--question", required=True)
    ask.add_argument("--proposed", required=True, help=t("help.decision_proposed"))
    ask.add_argument("--option", action="append", default=[], help=t("help.decision_option"))
    ask.add_argument("--reason", default="")
    ask.add_argument("--card", metavar="ID")
    ask.set_defaults(run=_ask)

    answer = actions.add_parser("answer", help=t("help.decision_answer"))
    answer.add_argument("id")
    answer.add_argument("answer", help=t("help.decision_answer_value"))
    answer.add_argument("--note", default="", help=t("help.note"))
    answer.add_argument("--free", action="store_true", help=t("help.decision_free"))
    answer.set_defaults(run=_answer)


def _load(ctx, id: str) -> Decision:
    try:
        return ctx.store.load_decision(id)
    except FileNotFoundError as error:
        raise context.CliError(t("decision.not_found", id=id)) from error


def _list(args) -> int:
    ctx = context.open(args, sync=False)
    items = [d for d in ctx.store.decisions() if args.all or d.answer is None]
    items.sort(key=lambda d: d.created)
    if args.json:
        print(json.dumps([d.to_meta() for d in items], ensure_ascii=False, indent=2))
    elif not items:
        print(t("cli.empty"))
    else:
        for d in items:
            print(t("decision.row", id=d.id, kind=d.kind, question=d.question, proposed=d.proposed))
    return 0


def _ask(args) -> int:
    if context.under_agent() and args.kind != AGENT_KIND:
        raise context.CliError(t("decision.agent_kind", kind=args.kind, allowed=AGENT_KIND))
    ctx = context.open(args)
    if args.kind not in DECISION_KINDS:
        raise context.CliError(t("decision.bad_kind", kind=args.kind, allowed=", ".join(DECISION_KINDS)))
    if args.card:
        load_card(ctx, args.card)
    decision = transitions.make_decision(
        ctx.store, kind=args.kind, question=args.question, proposed=args.proposed,
        options=args.option, reason=args.reason, card=args.card, now=ctx.now)
    ctx.write(f"decision ask {decision.id}", lambda: ctx.store.save_decision(decision))
    context.emit(args, {"id": decision.id}, decision.id)
    return 0


def _verdict_effect(ctx, decision: Decision, note: str):
    """What an answer to a verdict changes: the card and, on return, a new decision."""
    card = load_card(ctx, decision.card) if decision.card else None
    if card is None or decision.answer not in (vocab.ACCEPT, vocab.RETURN):
        return lambda: None
    store = ctx.store
    if decision.answer == vocab.ACCEPT:
        if card.status == "done":
            raise context.CliError(t("card.closed", card=card.id))
        card.status, card.closed_at, card.closed_by = "done", ctx.now, "owner"

        def accept() -> None:
            store.save_card(card)
            store.set_order([x for x in store.order() if x != card.id])
        return accept
    card.status = "returned"
    back = make_return_decision(store, card, note, ctx.now)

    def send_back() -> None:
        store.save_card(card)
        store.save_decision(back)
    return send_back


def _answer(args) -> int:
    context.refuse_agent()
    ctx = context.open(args)
    decision = _load(ctx, args.id)
    if decision.answer is not None:
        raise context.CliError(t("decision.answered", at=decision.answered_at))
    if args.answer not in decision.options and not args.free:
        raise context.CliError(t("decision.not_an_option", answer=args.answer,
                                 options=", ".join(decision.options)))
    decision.answer, decision.answered_at, decision.answered_by = args.answer, ctx.now, ctx.host
    decision.note = args.note or decision.note
    effect = _verdict_effect(ctx, decision, args.note) if decision.kind == "verdict" else (lambda: None)

    def apply() -> None:
        ctx.store.save_decision(decision)
        effect()

    ctx.write(f"decision answer {decision.id} {args.answer}", apply)
    context.emit(args, {"ok": True})
    return 0
