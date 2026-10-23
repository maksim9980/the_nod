"""`nod accept`: accepting a card — the result, the frames and the verdict question to the owner."""

import sys
from itertools import zip_longest

from the_nod import context, transitions
from the_nod.commands.card import load_card
from the_nod.i18n import t
from the_nod.model import ACCEPT_RESULTS


def add_parser(sub) -> None:
    accept = sub.add_parser("accept", help=t("help.accept"))
    accept.add_argument("card")
    accept.add_argument("--level", type=int, required=True, help=t("help.accept_level"))
    accept.add_argument("--result", required=True, help=" | ".join(ACCEPT_RESULTS))
    accept.add_argument("--evidence", default="", help=t("help.accept_evidence"))
    accept.add_argument("--frame", action="append", default=[], help=t("help.accept_frame"))
    accept.add_argument("--caption", action="append", default=[], help=t("help.accept_caption"))
    accept.add_argument("--step", action="append", default=[], help=t("help.accept_step"))
    accept.add_argument("--report", help=t("help.accept_report"))
    accept.set_defaults(run=_accept)


def _accept(args) -> int:
    context.refuse_agent()
    ctx = context.open(args)
    card = load_card(ctx, args.card)
    _, apply, warnings = transitions.make_acceptance(
        ctx.store, card, level=args.level, result=args.result, evidence=args.evidence,
        frames=list(zip_longest(args.frame, args.caption)), steps=args.step,
        report=args.report, now=ctx.now)
    ctx.write(f"accept {card.id} {args.result}", apply)
    for warning in warnings:
        print(warning, file=sys.stderr)
    context.emit(args, {"ok": True})
    return 0
