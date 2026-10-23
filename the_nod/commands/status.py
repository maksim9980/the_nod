"""`nod status`: the state snapshot — what waits, what runs, what changed."""

import json

from the_nod import context, snapshot
from the_nod.i18n import t

MAX_WIDTH = 100
_COUNTERS = ("runs", "steps_done", "accepted", "tokens")


def add_parser(sub) -> None:
    parser = sub.add_parser("status", help=t("help.status"))
    parser.add_argument("--since", help=t("help.status_since"))
    parser.add_argument("--no-sync", action="store_true", help=t("help.status_no_sync"))
    parser.add_argument("--peek", action="store_true", help=t("help.status_peek"))
    parser.set_defaults(run=run)


def _line(text: str) -> str:
    text = "  " + " ".join(text.split())
    return text if len(text) <= MAX_WIDTH else text[: MAX_WIDTH - 1] + "…"


def _block(title: str, rows: list[str]) -> list[str]:
    return [title, *(_line(r) for r in rows or [t("cli.empty")])]


def _changes(since: dict) -> list[str]:
    rows = []
    if any(since[k] for k in _COUNTERS):
        rows.append(t("status.counters", runs=since["runs"], steps=since["steps_done"],
                      accepted=since["accepted"], tokens=since["tokens"]))
    return rows + [t("status.closed", id=c["id"], title=c["title"], closed_at=c["closed_at"])
                   for c in since["cards_done"]]


def render(state: dict) -> str:
    """The short text of the snapshot: four blocks, a line per item; a stale state goes first."""
    waiting = [f"{d['id']}  {d['question']}  → {d['proposed']}" for d in state["waiting"]]
    running = [
        t("status.run_row", card=r["card"], title=r["card_title"], step=r["step"], step_title=r["step_title"],
          done=r["contracts_done"], total=r["contracts_total"])
        for r in state["running"]
    ]
    backlog = [
        f"{c['id']}  {c['title']}  [{c['status']}]  {c['steps_done']}/{c['steps_total']}"
        for c in state["backlog"]["top"]
    ]
    parts = [
        _block(t("status.waiting", count=len(waiting)), waiting),
        _block(t("status.running", count=len(running)), running),
        _block(t("status.since", since=state["since"]["from"]), _changes(state["since"])),
        _block(t("status.backlog", count=state["backlog"]["total"]), backlog),
    ]
    if not state["fresh"]:
        parts.insert(0, [t("status.stale", since=state["stale_since"])])
    return "\n".join(line for part in parts for line in part)


def run(args) -> int:
    ctx = context.open(args, sync=not args.no_sync)
    state = snapshot.build(ctx.store, now=ctx.now, host=ctx.host, since=args.since,
                           fresh=ctx.fresh, stale_since=ctx.stale_since)
    snapshot.write(ctx.store, state)
    # JSON is read by machines (the pane on a timer): only a human moves "While you were away".
    if not (args.json or args.peek):
        ctx.store.mark_seen(ctx.host, ctx.now)
    print(json.dumps(state, ensure_ascii=False, indent=2) if args.json else render(state))
    return 0
