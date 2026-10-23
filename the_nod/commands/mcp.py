"""`nod mcp`: an MCP server over stdio — the `nod` commands as agent tools."""

import sys
from pathlib import Path

from the_nod import context
from the_nod.i18n import t
from the_nod.mcp import server
from the_nod.paths import NotARepo


def add_parser(sub) -> None:
    parser = sub.add_parser("mcp", help=t("help.mcp"))
    parser.set_defaults(run=run)


def _root(given: str | None) -> str | None:
    """The state root. Without `--root` and without state it is `None`: the server starts, the core answers on a call.

    A refused explicit `--root` is not swallowed: the calls would silently look for the state from cwd.
    """
    try:
        return str(context.resolve_state_dir(given, Path.cwd()))
    except (context.CliError, NotARepo):
        if given is not None:
            raise
        return None


def run(args) -> int:
    return server.serve(_root(args.root), sys.stdin.buffer, sys.stdout.buffer)
