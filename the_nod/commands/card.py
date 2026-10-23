"""`nod card`: backlog cards — add, move, close, return, show."""

import json

from the_nod import context, transitions, vocab
from the_nod.i18n import t
from the_nod.model import CARD_SOURCES, Card, Decision

BY_CHOICES = ("owner", "agent")


def add_parser(sub) -> None:
    card = sub.add_parser("card", help=t("help.card"))
    actions = card.add_subparsers(dest="action", required=True)

    add = actions.add_parser("add", help=t("help.card_add"))
    add.add_argument("title", help=t("help.card_title"))
    add.add_argument("--body", default="", help=t("help.card_body"))
    add.add_argument("--source", choices=CARD_SOURCES, default="owner")
    add.add_argument("--top", action="store_true", help=t("help.card_top"))
    add.set_defaults(run=_add)

    move = actions.add_parser("move", help=t("help.card_move"))
    move.add_argument("id")
    place = move.add_mutually_exclusive_group(required=True)
    place.add_argument("--top", action="store_true")
    place.add_argument("--bottom", action="store_true")
    place.add_argument("--before", metavar="ID")
    place.add_argument("--after", metavar="ID")
    move.set_defaults(run=_move)

    close = actions.add_parser("close", help=t("help.card_close"))
    close.add_argument("id")
    close.add_argument("--by", choices=BY_CHOICES, default="owner")
    close.set_defaults(run=_close)

    back = actions.add_parser("return", help=t("help.card_return"))
    back.add_argument("id")
    back.add_argument("--note", required=True, help=t("help.card_return_note"))
    back.set_defaults(run=_return)

    show = actions.add_parser("show", help=t("help.card_show"))
    show.add_argument("id")
    show.set_defaults(run=_show)


def load_card(ctx, id: str) -> Card:
    try:
        return ctx.store.load_card(id)
    except FileNotFoundError as error:
        raise context.CliError(t("card.not_found", id=id)) from error
    except ValueError as error:
        if type(error) is not ValueError:  # cli.main handles LoadError and ModelError
            raise
        raise context.CliError(str(error)) from error


def _add(args) -> int:
    ctx = context.open(args)
    store = ctx.store
    card = Card(id=store.new_id("c"), title=args.title, status="backlog",
                created=ctx.now, source=args.source, body=args.body)

    def apply() -> None:
        order = store.order()  # before the save: `order()` would already list the new card
        store.save_card(card)
        store.set_order([card.id, *order] if args.top else [*order, card.id])

    ctx.write(f"card add {card.id}", apply)
    context.emit(args, {"id": card.id}, card.id)
    return 0


def _place(order: list[str], id: str, args) -> list[str]:
    rest = [x for x in order if x != id]
    if args.top:
        return [id, *rest]
    if args.bottom:
        return [*rest, id]
    target = args.before or args.after
    if target not in rest:
        raise context.CliError(t("card.not_in_backlog", id=target))
    at = rest.index(target) + (1 if args.after else 0)
    return [*rest[:at], id, *rest[at:]]


def _move(args) -> int:
    context.refuse_agent()
    ctx = context.open(args)
    load_card(ctx, args.id)
    order = ctx.store.order()
    if args.id not in order:
        raise context.CliError(t("card.not_in_backlog", id=args.id))
    new_order = _place(order, args.id, args)
    ctx.write(f"card move {args.id}", lambda: ctx.store.set_order(new_order))
    context.emit(args, {"ok": True})
    return 0


def _close(args) -> int:
    context.refuse_agent()
    ctx = context.open(args)
    card = load_card(ctx, args.id)
    if card.status == "done":
        raise context.CliError(t("card.closed_at", card=card.id, closed_at=card.closed_at))
    card.status, card.closed_at, card.closed_by = "done", ctx.now, args.by

    def apply() -> None:
        ctx.store.save_card(card)
        ctx.store.set_order([x for x in ctx.store.order() if x != card.id])

    ctx.write(f"card close {card.id}", apply)
    context.emit(args, {"ok": True})
    return 0


def make_return_decision(store, card: Card, note: str, now: str, *, reason: str = "") -> Decision:
    """The "return" decision: shared by `card return`, `decision answer` on a verdict and the driver.

    `note` is only ever the owner's; the driver puts its own text (why the card came back) into `reason`.
    """
    return Decision(id=store.new_id("d"), kind="return", created=now,
                    question=t("card.return_question", title=card.title), proposed=vocab.RERUN,
                    options=[vocab.RERUN, vocab.BACKLOG], reason=reason, card=card.id, note=note)


def _return(args) -> int:
    context.refuse_agent()
    ctx = context.open(args)
    card = load_card(ctx, args.id)
    if card.status == "returned":
        raise context.CliError(t("card.returned", card=card.id))
    run = transitions.open_run(ctx.store, card.id)
    # The run ends with `stop` in the same commit: an open run of a returned card would hold the driver queue.
    close_run = (transitions.stop_run(ctx.store, run, note=args.note, now=ctx.now)
                 if run is not None else None)
    card.status = "returned"
    decision = make_return_decision(ctx.store, card, args.note, ctx.now)

    def apply() -> None:
        if close_run is not None:
            close_run()
        ctx.store.save_card(card)
        ctx.store.save_decision(decision)

    ctx.write(f"card return {card.id}", apply)
    context.emit(args, {"ok": True})
    return 0


def _render(card: Card) -> str:
    lines = [card.title, t("card.show_status", status=card.status)]
    if card.brief:
        lines += ["", t("card.show_brief"), card.brief]
    if card.steps:
        lines += ["", t("card.show_steps"),
                  *(f"  {s.n}. [{'x' if s.done else ' '}] {s.title}" for s in card.steps)]
    if card.body.strip():
        lines += ["", card.body.strip()]
    return "\n".join(lines)


def _show(args) -> int:
    ctx = context.open(args, sync=False)
    card = load_card(ctx, args.id)
    if args.json:
        print(json.dumps({**card.to_meta(), "body": card.body}, ensure_ascii=False, indent=2))
    else:
        print(_render(card))
    return 0
