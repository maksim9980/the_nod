"""The `nod` entry point: argument parsing and one way to print errors."""

import argparse
import sys

from the_nod import i18n
from the_nod.commands import (accept, card, decision, doctor, driver, import_, init, install, mcp,
                              migrate, render, review, run, status)
from the_nod.context import CliError, Stale
from the_nod.gitsync import GitError, ProtectedBranch
from the_nod.i18n import t
from the_nod.model import ModelError
from the_nod.paths import NotARepo
from the_nod.store import LoadError

COMMANDS = (init, card, decision, status, run, accept, render, driver, review, doctor, install, mcp,
            import_, migrate)
EXIT_ERROR = 2
EXIT_REFUSED = 3


def _json_everywhere(parser: argparse.ArgumentParser) -> None:
    """`--json` after a subcommand too; without the flag the top-level value is not overwritten."""
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for child in action.choices.values():
            child.add_argument("--json", action="store_true", dest="json",
                               default=argparse.SUPPRESS, help=t("help.json"))
            _json_everywhere(child)


def build_parser() -> argparse.ArgumentParser:
    """The parser in the current language: help follows NOD_LANG only, it is built before the manifest is read."""
    parser = argparse.ArgumentParser(prog="nod", description="Nod")
    parser.add_argument("--root", help=t("help.root"))
    parser.add_argument("--json", action="store_true", help=t("help.json"))
    sub = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        command.add_parser(sub)
    _json_everywhere(parser)
    return parser


def _describe(error: Exception) -> str:
    if not isinstance(error, LoadError):
        return str(error)
    text = str(error).removeprefix(f"{error.path}: ")
    where = str(error.path) if error.line is None else f"{error.path}:{error.line}"
    return f"{text} ({where})"


def _use_utf8() -> None:
    """Non-ASCII output reads in a Windows console without environment variables."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass


def _error(message: object) -> None:
    print(t("cli.error", message=message), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    _use_utf8()
    try:
        # Every call starts from the environment: in the MCP server one process serves many calls.
        i18n.use(i18n.resolve())
    except i18n.LangError as error:
        i18n.use(i18n.DEFAULT)
        _error(error)
        return EXIT_ERROR
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return args.run(args)
    except (Stale, ProtectedBranch) as error:
        _error(error)
        return EXIT_REFUSED
    except (LoadError, ModelError, NotARepo, CliError, GitError) as error:
        _error(_describe(error))
        return EXIT_ERROR
    except ValueError as error:  # an invalid id, a broken manifest and other Store refusals
        _error(error)
        return EXIT_ERROR
    except OSError as error:  # a folder instead of a file, a busy file, no permission
        where = f": {error.filename}" if error.filename else ""
        _error(f"{error.strerror or error}{where}")
        return EXIT_ERROR
