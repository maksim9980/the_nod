"""`nod render`: prints BACKLOG.md and BACKLOG-ARCHIVE.md from `.nod`."""

from pathlib import Path

from the_nod import context, render
from the_nod.i18n import t
from the_nod.store import write_text_atomic

_VIEWS = {"backlog": render.backlog, "archive": render.archive}


def add_parser(sub) -> None:
    parser = sub.add_parser("render", help=t("help.render"))
    parser.add_argument("view", choices=sorted(_VIEWS))
    parser.add_argument("--write", metavar=t("help.render_path"), help=t("help.render_write"))
    parser.set_defaults(run=run)


def run(args) -> int:
    """Neither changes nor commits the state: a project file is not state."""
    if args.write is not None:
        context.refuse_agent()  # `--write` takes any path: card text must not land in the agent's chosen file
    ctx = context.open(args)
    text = _VIEWS[args.view](ctx.store)
    if args.write is None:
        print(text, end="")
        return 0
    write_text_atomic(Path(args.write), text)
    print(t("render.written", path=args.write))
    return 0
