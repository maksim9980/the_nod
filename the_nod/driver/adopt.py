"""A brief the agent wrote but did not commit or did not put into the result file.

The agent may stop before the commit and the TOML: the budget or the turns ran out. The driver then looks
for a brief candidate in the adapter briefs folder itself: a `*.md` file that `git status` shows as new or
changed inside the command window. The window starts at the mtime of the prompt file (`launch` writes it
before the start) and ends at the mtime of the `.out.txt` output file (`run_agent` writes it after the command).
The driver commits an adopted brief in its own `docs(brief): <slug>` commit before the state write.
"""

from collections.abc import Callable
from pathlib import Path, PurePosixPath

from the_nod.adapters import briefs
from the_nod.context import Context
from the_nod.driver import files, results
from the_nod.driver.log import Log
from the_nod.gitsync import GitError, ProtectedBranch
from the_nod.i18n import t
from the_nod.model import Card

SKIP_SUFFIXES = (".plan.md", ".verdict.md")

Parsed = tuple[str, list[str], list[briefs.Fork]]


def _read(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise ValueError(t("driver.brief_file_unreadable", path=rel, error=err)) from err


def parse(root: Path, value: str) -> Parsed:
    """The brief path from the root, the steps and the forks; `ValueError` with the reason."""
    rel = files.brief_path(root, value)
    parsed = briefs.parse_brief(_read(root, rel))
    steps = briefs.require_steps(parsed)
    return rel, steps, briefs.parse_forks(parsed.decisions)


def _key(title: str) -> str:
    return " ".join(title.split()).casefold()


def same_title(root: Path, rel: str, title: str) -> bool:
    """The `# …` title of the brief matches the card title, ignoring case and spaces."""
    try:
        return _key(briefs.parse_brief(_read(root, rel)).title) == _key(title)
    except ValueError:
        return False


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def candidate(ctx: Context, log: Log, briefs_dir: str, since: float, until: float | None = None,
              accept: Callable[[str], bool] = lambda rel: True) -> str | None:
    """The newest uncommitted `<briefs_dir>/*.md` with an mtime in `[since, until]` that passes `accept`."""
    if ctx.sync is None:
        return None
    folder = briefs_dir.strip("/")
    try:
        changed = ctx.sync.changed(folder)
    except GitError as err:
        log.warn(t("driver.candidate_not_found", error=err))
        return None
    root = files.repo_root(ctx.store)
    found = []
    for rel in changed:
        path = PurePosixPath(rel)
        if str(path.parent) != folder or path.suffix != ".md" or rel.endswith(SKIP_SUFFIXES):
            continue
        mtime = _mtime(root / rel)
        if mtime is not None and mtime >= since and (until is None or mtime <= until):
            found.append((mtime, rel))
    return next((rel for _, rel in sorted(found, reverse=True) if accept(rel)), None)


def adopt(ctx: Context, card: Card, rel: str) -> Parsed:
    """Parses the brief, commits it if it is not committed and writes the result file; `ValueError` with the reason."""
    parsed = parse(files.repo_root(ctx.store), rel)
    path = parsed[0]
    if ctx.sync is not None:
        try:
            ctx.sync.commit_paths([path], f"docs(brief): {PurePosixPath(path).stem}")
        except (GitError, ProtectedBranch) as err:
            raise ValueError(t("driver.brief_not_committed", path=path, error=err)) from err
    result = files.result_path(ctx.store, card.id, "brief")
    text = f'brief = "{path}"\n'
    if not result.exists() or result.read_text(encoding="utf-8") != text:
        result.write_text(text, encoding="utf-8")
    return parsed


def _previous_result(ctx: Context, log: Log, card: Card, since: float | None) -> Parsed | None:
    """The result file of the last attempt, or one written by hand: the path to a brief with steps."""
    path = files.result_path(ctx.store, card.id, "brief")
    written = _mtime(path)
    if written is None or (since is not None and written < since):
        return None
    try:
        rel = results.read_brief(path).brief
        if not rel:
            return None
        parsed = adopt(ctx, card, rel)
    except (results.ResultError, ValueError) as err:
        log.warn(t("driver.previous_result_rejected", card=card.id, error=err))
        return None
    log.info(t("driver.previous_result_adopted", card=card.id, path=parsed[0]))
    return parsed


def _previous_file(ctx: Context, log: Log, briefs_dir: str, card: Card, since: float) -> Parsed | None:
    """A brief candidate in the window of the last command; without `.out.txt` there is no window, only a brief with the card title."""
    until = _mtime(files.output_paths(ctx.store, card.id, "brief")[0])
    root = files.repo_root(ctx.store)
    if until is None:
        rel = candidate(ctx, log, briefs_dir, since, accept=lambda r: same_title(root, r, card.title))
    else:
        rel = candidate(ctx, log, briefs_dir, since, until)
    if rel is None:
        return None
    try:
        parsed = adopt(ctx, card, rel)
    except ValueError as err:
        log.warn(t("driver.previous_brief_rejected", card=card.id, path=rel, error=err))
        return None
    log.info(t("driver.previous_brief_adopted", card=card.id, path=parsed[0]))
    return parsed


def before_command(ctx: Context, log: Log, briefs_dir: str, card: Card) -> Parsed | None:
    """A brief of the last attempt that the driver missed. `None` means: run the command.

    First the result file (a repeated pass or a path written by hand), then a brief candidate.
    A rebrief (`card.brief` is not empty) always goes through the command.
    """
    if card.brief:
        return None
    since = _mtime(files.prompt_path(ctx.store, card.id, "brief"))
    parsed = _previous_result(ctx, log, card, since)
    if parsed is None and since is not None:
        parsed = _previous_file(ctx, log, briefs_dir, card, since)
    return parsed


def after_command(ctx: Context, log: Log, briefs_dir: str, card: Card,
                  failure: str = "") -> tuple[Parsed | None, str]:
    """A brief without the result file; the second item is why the candidate is not accepted, or empty.

    `failure` is a failure of the command process: the brief is still adopted, the reason goes to the log.
    """
    since = _mtime(files.prompt_path(ctx.store, card.id, "brief"))
    rel = candidate(ctx, log, briefs_dir, since) if since is not None else None
    if rel is None:
        return None, ""
    try:
        parsed = adopt(ctx, card, rel)
    except ValueError as err:
        return None, t("driver.candidate_rejected", path=rel, error=err)
    if failure:
        log.info(t("driver.no_result_adopted_after", card=card.id, path=parsed[0], failure=failure))
    else:
        log.info(t("driver.no_result_adopted", card=card.id, path=parsed[0]))
    return parsed, ""
