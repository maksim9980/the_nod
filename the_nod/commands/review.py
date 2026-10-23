"""`nod review`: the weekly review — the numbers of a period, suggestions and their status."""

from dataclasses import replace
from datetime import datetime

from the_nod import context, vocab
from the_nod.context import CliError
from the_nod.i18n import t
from the_nod.review import render
from the_nod.review.collect import collect
from the_nod.review.rules import merge_status, suggest


def add_parser(sub) -> None:
    review = sub.add_parser("review", help=t("help.review"))
    actions = review.add_subparsers(dest="action", required=True)
    week = actions.add_parser("week", help=t("help.review_week"))
    week.add_argument("--since", help=t("help.review_since"))
    week.set_defaults(run=_week)
    mark = actions.add_parser("mark", help=t("help.review_mark"))
    mark.add_argument("week", help=t("help.review_mark_week"))
    mark.add_argument("n", type=int, help=t("help.review_mark_n"))
    status = mark.add_mutually_exclusive_group(required=True)
    status.add_argument("--applied", action="store_true", help=t("help.review_mark_status", status=vocab.APPLIED))
    status.add_argument("--proposed", action="store_true", help=t("help.review_mark_status", status=vocab.PROPOSED))
    mark.set_defaults(run=_mark)


def _since(args, now: str) -> str:
    """Period start: `--since` or a week ago; a bad date, a date with a zone or one not before `now` is a `CliError`."""
    if args.since is None:
        return render.default_since(now)
    try:
        since = datetime.fromisoformat(args.since)
    except ValueError:
        raise CliError(t("review.bad_since", value=args.since)) from None
    if since.tzinfo is not None:
        raise CliError(t("review.bad_since", value=args.since))
    if since >= datetime.fromisoformat(now):
        raise CliError(t("review.since_not_before", value=args.since, now=now))
    return args.since


def _week(args) -> int:
    ctx = context.open(args)
    until = ctx.now
    since = _since(args, until)
    subjects = ctx.sync.log_subjects(since) if ctx.sync else []
    stats = collect(ctx.store, since=since, until=until, subjects=subjects)
    week = render.week_id(until)
    old = ctx.store.load_review(week)
    suggestions = merge_status(suggest(stats), old.suggestions if old else [])
    review = render.to_review(stats, suggestions, week=week, now=ctx.now)
    rel = f"reviews/{week}.md"
    ctx.write(f"review week {week}", lambda: ctx.store.save_review(review))
    context.emit(args, {**review.to_meta(), "path": rel}, render.summary(review, rel))
    return 0


def _mark(args) -> int:
    ctx = context.open(args)
    review = ctx.store.load_review(args.week)
    if review is None:
        raise CliError(t("review.no_review", week=args.week))
    if not any(s.n == args.n for s in review.suggestions):
        raise CliError(t("review.no_suggestion", week=args.week, n=args.n))
    status = vocab.APPLIED if args.applied else vocab.PROPOSED
    marked = replace(
        review,
        suggestions=[replace(s, status=status) if s.n == args.n else s for s in review.suggestions],
        body=render.mark_body(review.body, args.n, status))
    ctx.write(f"review mark {args.week} {args.n} {status}", lambda: ctx.store.save_review(marked))
    context.emit(args, {"week": args.week, "n": args.n, "status": status}, t("review.marked", n=args.n, status=status))
    return 0
