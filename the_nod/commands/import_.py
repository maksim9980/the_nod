"""`nod import`: cards from another format — now a markdown file with `##` headings."""

import sys
from pathlib import Path

from the_nod import context
from the_nod.i18n import t
from the_nod.importers import markdown
from the_nod.model import Card


def add_parser(sub) -> None:
    parser = sub.add_parser("import", help=t("importer.help"))
    formats = parser.add_subparsers(dest="format", required=True)
    md = formats.add_parser("markdown", help=t("importer.help_markdown"))
    md.add_argument("--from", dest="source", required=True, metavar="FILE", help=t("importer.help_from"))
    md.add_argument("--dry-run", action="store_true", help=t("importer.help_dry_run"))
    md.set_defaults(run=run)


def _read(path: Path) -> str:
    """The file as UTF-8, a BOM accepted."""
    if not path.is_file():
        raise context.CliError(t("importer.no_file", path=path))
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise context.CliError(t("importer.not_utf8", path=path)) from error


def _key(title: str) -> str:
    """Titles match without case and spacing differences."""
    return " ".join(title.split()).casefold()


def run(args) -> int:
    """Adds a backlog card per heading, at the end of the order; a title that is already a card is skipped."""
    context.refuse_agent()
    ctx = context.open(args, sync=not args.dry_run)  # a dry run touches neither git nor the files
    path = Path(args.source)
    known = {_key(card.title) for card in ctx.store.cards()}
    new: list[tuple[str, str]] = []
    skipped: list[str] = []
    lines: list[str] = []
    entries = markdown.parse(_read(path))
    if not entries:  # otherwise "imported 0" reads the same as "all of it was known"
        print(t("importer.no_headings", path=path), file=sys.stderr)
    for title, body in entries:
        if _key(title) in known:
            skipped.append(title)
            lines.append(t("importer.skipped", title=title))
            continue
        known.add(_key(title))  # a title repeated in the file is skipped as well
        new.append((title, body))
        if args.dry_run:
            lines.append(t("importer.would_import", title=title))

    if args.dry_run:
        lines.append(t("importer.dry_run_summary", count=len(new)))
        data = {"would_import": [title for title, _ in new], "skipped": skipped}
    else:
        if new:
            ctx.write(f"import markdown {path.name}", lambda: _save(ctx, new))
        lines.append(t("importer.imported", count=len(new)))
        data = {"imported": len(new), "skipped": skipped}
    context.emit(args, data, "\n".join(lines))
    return 0


def _save(ctx, new: list[tuple[str, str]]) -> None:
    store = ctx.store
    order = store.order()  # before the new cards: `order()` would put them last in the id order
    ids = []
    for title, body in new:
        card = Card(id=store.new_id("c"), title=title, status="backlog", created=ctx.now,
                    source="import", body=body)
        store.save_card(card)
        ids.append(card.id)
    store.set_order([*order, *ids])
