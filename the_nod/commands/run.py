"""`nod run`: the runs of a card — start, progress, finish."""

from the_nod import context, transitions
from the_nod.commands.card import load_card
from the_nod.i18n import t
from the_nod.model import Run
from the_nod.transitions import RESULTS, RunUsage


def add_parser(sub) -> None:
    run = sub.add_parser("run", help=t("help.run"))
    actions = run.add_subparsers(dest="action", required=True)

    start = actions.add_parser("start", help=t("help.run_start"))
    start.add_argument("card")
    start.add_argument("--step", type=int, help=t("help.run_step"))
    start.add_argument("--contracts", type=int, default=0, help=t("help.run_contracts"))
    start.set_defaults(run=_start)

    progress = actions.add_parser("progress", help=t("help.run_progress"))
    progress.add_argument("id")
    progress.add_argument("--contracts-done", type=int, required=True)
    progress.set_defaults(run=_progress)

    finish = actions.add_parser("finish", help=t("help.run_finish"))
    finish.add_argument("id")
    finish.add_argument("--result", required=True, help=" | ".join(RESULTS))
    for name in ("contracts-done", "tokens", "minutes", "agents", "tool-errors"):
        finish.add_argument(f"--{name}", type=int, default=0)
    finish.add_argument("--note", default="", help=t("help.note"))
    finish.set_defaults(run=_finish)


def _start(args) -> int:
    ctx = context.open(args)
    card = load_card(ctx, args.card)
    run, apply = transitions.start_run(ctx.store, card, step=args.step,
                                       contracts=args.contracts, now=ctx.now)
    ctx.write(f"run start {run.id}", apply)
    context.emit(args, {"id": run.id}, run.id)
    return 0


def _load_run(ctx, id: str) -> Run:
    try:
        return ctx.store.load_run(id)
    except FileNotFoundError as error:
        raise context.CliError(t("run.not_found", id=id)) from error


def _progress(args) -> int:
    ctx = context.open(args)
    run = _load_run(ctx, args.id)
    apply = transitions.progress_run(ctx.store, run, contracts_done=args.contracts_done, now=ctx.now)
    ctx.write(f"run progress {run.id} {args.contracts_done}", apply)
    context.emit(args, {"ok": True})
    return 0


def _finish(args) -> int:
    context.refuse_agent()
    ctx = context.open(args)
    transitions.check_result(args.result)
    run = _load_run(ctx, args.id)
    if run.finished is not None:
        raise context.CliError(t("transitions.run_finished", finished=run.finished))
    card = load_card(ctx, run.card)
    usage = RunUsage(args.contracts_done, args.tokens, args.minutes, args.agents, args.tool_errors)
    apply = transitions.finish_run(ctx.store, run, card, result=args.result, usage=usage,
                                   note=args.note, now=ctx.now)
    ctx.write(f"run finish {run.id} {args.result}", apply)
    context.emit(args, {"ok": True})
    return 0
