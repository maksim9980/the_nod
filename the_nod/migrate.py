"""Moving the state of the older version: `.sprintboot/` becomes `.nod/`.

The older version wrote Russian identifiers into the state files, and the model rejects them
now. The rewrite works on the frontmatter (`the_nod.frontmatter`), not on the model classes,
and touches only the fields that held those identifiers; fork options are free text and stay.
`plan` reads and checks, `apply` writes: every refusal comes before anything changed, and a
failure after the move puts everything back.

A second machine pulls the migration and keeps its local files (snapshot, driver log, "seen"
times) in the older folder: there `plan` moves just those files into `.nod/`.
"""

import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from the_nod import frontmatter, harness, vocab
from the_nod.errors import HarnessError
from the_nod.files import write_text_atomic
from the_nod.frontmatter import FrontmatterError
from the_nod.gitsync import LOCAL_FILES, GitError, GitSync, ProtectedBranch
from the_nod.i18n import t
from the_nod.model import SUGGESTION_STATUSES, Acceptance, Card, Decision, ModelError, Review, Run, Spend
from the_nod.paths import NO_WINDOW, STATE_DIR_NAME, NotARepo, main_worktree_root
from the_nod.store import LoadError

LEGACY_DIR = ".sprintboot"
LEGACY_VALUES: dict[str, str] = {
    "сделано": vocab.DONE,
    "отложить": vocab.POSTPONE,
    "да": vocab.YES,
    "нет": vocab.NO,
    "подождать": vocab.WAIT,
    "решилась": vocab.SOLVED,
    "не решилась": vocab.UNSOLVED,
    "не проверено": vocab.UNVERIFIED,
    "предлагается": vocab.PROPOSED,
    "внесено": vocab.APPLIED,
}
# Marker lines in the body of a decision: the driver applied the answer / made the card of a `pain`.
LEGACY_MARKS: dict[str, str] = {"Учтено:": vocab.CONSUMED_MARK, "Карточка:": vocab.CARD_MARK}
# The older version spoke Russian only: a manifest without `lang` keeps speaking it.
LEGACY_LANG = "ru"
SUBJECT = f"state: migrate {LEGACY_DIR} to {STATE_DIR_NAME}"
GITIGNORE = ".gitignore"
# Decision kinds whose answers were identifiers; the others were English already or free text.
VALUE_KINDS = ("owner-action", "next-batch", "pain")
VALUE_FIELDS = ("answer", "proposed")
# A manifest line that still calls the older command, package or environment variables.
OLD_NAME = re.compile(r"\bsb\b|sprintboot|(?<![A-Za-z0-9])SB_", re.IGNORECASE)
MAX_LISTED = 5
# Local files met in both folders: the snapshot is rebuilt anyway, the "seen" times are merged.
DERIVED = ("state.json",)
MERGED = ("seen.toml",)

_MARK = re.compile(r"^(\s*)(%s)" % "|".join(map(re.escape, LEGACY_MARKS)), re.MULTILINE)
_OLD_STATUSES = "|".join(old for old, new in LEGACY_VALUES.items() if new in SUGGESTION_STATUSES)
_REVIEW_MARK = re.compile(rf"^(\d+)\. \[({_OLD_STATUSES})\]", re.MULTILINE)
_TABLE = re.compile(r"^\s*\[\[?\s*([^\]]+?)\s*\]")
_ADAPTER = re.compile(r"^\s*adapter\s*=")
_NEEDS_SB = re.compile(r"^(\s*)sb(\s*=)")
_DOTTED_SB = re.compile(r"^(\s*needs\s*\.\s*)sb(\s*=)")
_INLINE_NEEDS = re.compile(r"^\s*needs\s*=\s*\{")
_INLINE_SB = re.compile(r"([{,]\s*)sb(\s*=)")
_IGNORED = re.compile(r"^(\s*!?/?)%s(?=/|\s*$)" % re.escape(LEGACY_DIR), re.MULTILINE)
_REPORT_PREFIXES = (f"{LEGACY_DIR}/", f"{LEGACY_DIR}\\")


class MigrateError(ValueError):
    """A refusal, or a failure that was undone: nothing was changed."""


class PullFailed(RuntimeError):
    """The branch could not be brought up to date with origin before the migration: nothing moved."""


@dataclass(frozen=True)
class Rewrite:
    """A state file with the older values replaced; `path` is from the state folder, with `/`."""

    path: str
    text: str


@dataclass(frozen=True)
class Manifest:
    """What happens to `harness.toml`; `text` is `None` when the file stays as it is."""

    text: str | None = None
    adapter: str | None = None  # the adapter this version does not have, replaced by "default"
    needs_renamed: bool = False
    lang_added: bool = False
    git_added: bool = False
    push: bool = False  # `[git] push` after the migration
    old_names: tuple[tuple[int, str], ...] = ()  # (line number, line) naming the older version


@dataclass(frozen=True)
class LocalFiles:
    """A machine that pulled the migration: its local files go from the older folder to `.nod/`.

    Paths are from the folder, with `/`. `merged` holds the merged text of each file.
    """

    moves: tuple[str, ...] = ()
    merged: tuple[tuple[str, str], ...] = ()
    dropped: tuple[str, ...] = ()  # an older snapshot next to a newer one
    kept: tuple[str, ...] = ()  # `.nod/` has its own: the file stays where it is


@dataclass(frozen=True)
class MigrationPlan:
    git: bool  # the folder is in a git repository: the move becomes one commit
    tracked: bool = False  # the older folder is in the index: `git mv`, otherwise `os.replace`
    rewrites: tuple[Rewrite, ...] = ()
    manifest: Manifest = Manifest()
    gitignore: str | None = None  # the new `.gitignore`, `None` when it stays
    gitignore_lines: int = 0
    origin: bool = False  # the repo has an `origin` remote
    local: LocalFiles | None = None  # set: only this machine's local files move, nothing is committed

    @property
    def pulls(self) -> bool:
        """`push = true` comes with the migration and there is an origin: pull before anything moves."""
        return self.local is None and self.git and self.origin and self.manifest.push


# --- git ---

def _run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
    except OSError as err:
        raise GitError(t("git.not_found")) from err


def _git(repo: Path, *args: str) -> str:
    result = _run(repo, *args)
    if result.returncode != 0:
        raise GitError(f"git {args[0]}: {result.stderr.strip()}")
    return result.stdout


def _in_git(repo: Path) -> bool:
    try:
        main_worktree_root(repo)
    except NotARepo:
        return False
    return True


def _check_branch(repo: Path) -> None:
    """The move is committed on a work branch: `main` and `master` refuse, as every state write does."""
    sync = GitSync(repo, LEGACY_DIR, remote=False)
    branch = sync.branch()  # GitError on a detached HEAD
    if sync.is_protected(branch):
        raise ProtectedBranch(t("git.protected_state", branch=branch))


def _listed(paths: list[str]) -> str:
    more = ", …" if len(paths) > MAX_LISTED else ""
    return ", ".join(paths[:MAX_LISTED]) + more


def _check_clean(repo: Path, gitignore_changes: bool) -> bool:
    """Refuses uncommitted files of the older folder (local ones aside) and of a `.gitignore` to rewrite.

    The migration commit takes these paths whole: someone's unfinished edit would go into it.
    Returns whether the older folder is in the index.
    """
    sync = GitSync(repo, LEGACY_DIR, remote=False)
    dirty = sync.dirty() + (sync.changed(GITIGNORE) if gitignore_changes else [])
    if dirty:
        raise MigrateError(t("migrate.dirty", files=_listed(dirty)))
    return bool(_git(repo, "ls-files", "-z", "--", LEGACY_DIR))


def _tracked_anywhere(repo: Path) -> bool:
    """The older folder is in the index or in HEAD (a branch without commits has no HEAD)."""
    head = _run(repo, "ls-tree", "-r", "--name-only", "HEAD", "--", LEGACY_DIR)
    return bool(_git(repo, "ls-files", "--", LEGACY_DIR)) or (head.returncode == 0 and bool(head.stdout))


# --- the state files ---

def _value(value: object) -> object:
    return LEGACY_VALUES.get(value, value) if isinstance(value, str) else value


def _decision(meta: dict, body: str) -> tuple[dict, str]:
    if meta.get("kind") in VALUE_KINDS:
        changed = {key: _value(meta[key]) for key in VALUE_FIELDS if key in meta}
        if isinstance(meta.get("options"), list):
            changed["options"] = [_value(option) for option in meta["options"]]
        meta = {**meta, **changed}
    return meta, _MARK.sub(lambda m: m.group(1) + LEGACY_MARKS[m.group(2)], body)


def _acceptance(meta: dict, body: str) -> tuple[dict, str]:
    """The result, and a report path inside the older folder that moves with it."""
    changed = {"result": _value(meta["result"])} if "result" in meta else {}
    report = meta.get("report")
    if isinstance(report, str) and report.startswith(_REPORT_PREFIXES):
        changed["report"] = STATE_DIR_NAME + report[len(LEGACY_DIR):]
    return {**meta, **changed}, body


def _suggestion(item: object) -> object:
    if isinstance(item, dict) and "status" in item:
        return {**item, "status": _value(item["status"])}
    return item


def _review(meta: dict, body: str) -> tuple[dict, str]:
    """Statuses in the frontmatter and in the `N. [status]` lines; the headings of the body stay."""
    if isinstance(meta.get("suggestions"), list):
        meta = {**meta, "suggestions": [_suggestion(item) for item in meta["suggestions"]]}
    return meta, _REVIEW_MARK.sub(lambda m: f"{m.group(1)}. [{LEGACY_VALUES[m.group(2)]}]", body)


# The model files of the state: their class and the fix of the older values (`None`: nothing to fix).
_FOLDERS = (
    ("cards/*.md", Card, None),
    ("decisions/*.md", Decision, _decision),
    ("runs/*.md", Run, None),
    ("acceptance/*/index.md", Acceptance, _acceptance),
    ("reviews/*.md", Review, _review),
    ("usage/*.md", Spend, None),
)


def _read(path: Path) -> tuple[dict, str]:
    try:
        return frontmatter.parse(path.read_text(encoding="utf-8-sig"))
    except FrontmatterError as error:
        raise LoadError(str(error), path, error.line) from error


def _dump(path: Path, meta: dict, body: str) -> str:
    try:
        return frontmatter.dump(meta, body)
    except FrontmatterError as error:
        raise LoadError(str(error), path) from error


def _rewrites(state: Path) -> list[Rewrite]:
    """The files whose older values change; every model file must read once they have changed."""
    found = []
    for pattern, cls, fix in _FOLDERS:
        for path in sorted(state.glob(pattern)):
            meta, body = _read(path)
            new_meta, new_body = fix(meta, body) if fix else (meta, body)
            try:
                cls.from_meta(new_meta, new_body)
            except ModelError as error:
                raise LoadError(t("migrate.invalid", error=error), path) from error
            if (new_meta, new_body) != (meta, body):
                found.append(Rewrite(path.relative_to(state).as_posix(), _dump(path, new_meta, new_body)))
    return found


# --- the manifest and .gitignore ---

def _toml(text: str, path: Path) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise LoadError(t("migrate.bad_manifest", error=" ".join(str(error).split())), path) from error


def _eol(line: str) -> str:
    return line[len(line.rstrip("\r\n")):]


def _ended(lines: list[str]) -> list[str]:
    """The lines with the last one ended by a newline, so that a line can follow it."""
    if lines and not lines[-1].endswith("\n"):
        return [*lines[:-1], lines[-1] + "\n"]
    return lines


def _needs_key(line: str, table: str | None) -> str:
    """`sb` renamed to `nod` in the `[needs]` table, a dotted `needs.sb` or an inline `needs = { … }`."""
    if table == "needs":
        return _NEEDS_SB.sub(r"\1nod\2", line, count=1)
    if table is None and _DOTTED_SB.match(line):
        return _DOTTED_SB.sub(r"\1nod\2", line, count=1)
    if table is None and _INLINE_NEEDS.match(line):
        return _INLINE_SB.sub(r"\1nod\2", line)
    return line


def _manifest_lines(lines: list[str], unknown_adapter: bool) -> tuple[list[str], bool]:
    """The lines with the adapter set to "default" (when unknown) and the `[needs]` key `sb` renamed to `nod`."""
    table: str | None = None
    out: list[str] = []
    renamed = False
    for line in lines:
        header = _TABLE.match(line)
        if header:
            table = header.group(1)
            out.append(line)
        elif table is None and unknown_adapter and _ADAPTER.match(line):
            out.append(f'adapter = "{harness.ADAPTERS[0]}"' + _eol(line))
        else:
            new = _needs_key(line, table)
            renamed = renamed or new != line
            out.append(new)
    return out, renamed


def _with_lang(lines: list[str]) -> list[str]:
    """`lang = "ru"` before the first key or table: a top-level key cannot follow a table."""
    at = next((i for i, line in enumerate(lines) if line.strip() and not line.lstrip().startswith("#")), None)
    if at is None:
        return [*_ended(lines), f'lang = "{LEGACY_LANG}"\n']
    return [*lines[:at], f'lang = "{LEGACY_LANG}"\n', *lines[at:]]


def _push_on(data: dict) -> bool:
    table = data.get("git", {})
    return isinstance(table, dict) and table.get("push", False) is True


def _manifest(path: Path) -> Manifest:
    """The manifest after the migration, checked as `nod` will read it; lines naming the older version
    are reported, not changed.

    Without a `[git]` table the older version pushed after every write: `push = true` keeps that.
    """
    if not path.is_file():
        return Manifest()
    text = path.read_text(encoding="utf-8-sig")
    data = _toml(text, path)
    adapter = data.get("adapter", harness.ADAPTERS[0])
    unknown = adapter not in harness.ADAPTERS
    lines, renamed = _manifest_lines(text.splitlines(keepends=True), unknown)
    lang_added = "lang" not in data
    if lang_added:
        lines = _with_lang(lines)
    git_added = "git" not in data
    if git_added:
        lines = [*_ended(lines), "\n[git]\npush = true\n"]
    new = "".join(lines)
    new_data = _toml(new, path)
    try:
        harness.validate(new_data)
    except HarnessError as error:
        raise MigrateError(t("migrate.manifest_invalid", error=error)) from error
    old_names = tuple((n, line.strip()) for n, line in enumerate(new.splitlines(), start=1)
                      if not line.lstrip().startswith("#") and OLD_NAME.search(line))
    return Manifest(new if new != text else None, str(adapter) if unknown else None, renamed, lang_added,
                    git_added, _push_on(new_data), old_names)


def _gitignore(path: Path) -> tuple[str | None, int]:
    """`.gitignore` with the lines of the older folder pointing to `.nod/`, and how many lines changed."""
    if not path.is_file():
        return None, 0
    text = path.read_text(encoding="utf-8")
    new, count = _IGNORED.subn(lambda m: m.group(1) + STATE_DIR_NAME, text)
    return (new if count else None), count


# --- a machine that pulled the migration ---

def _is_local(rel: str) -> bool:
    return any(rel == name or rel.startswith(f"{name}/") for name in LOCAL_FILES)


def _merge_flat(older: Path, newer: Path) -> str | None:
    """Two flat TOML files as one, the newer value winning; `None` when one does not read as such."""
    try:
        merged = {**tomllib.loads(older.read_text(encoding="utf-8-sig")),
                  **tomllib.loads(newer.read_text(encoding="utf-8-sig"))}
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    if not all(isinstance(value, str) for value in merged.values()):
        return None
    return frontmatter.toml_flat(merged)


def _local_files(repo: Path, git: bool) -> LocalFiles | None:
    """What goes to `.nod/` when the older folder holds only local files and git tracks none of it there."""
    legacy, target = repo / LEGACY_DIR, repo / STATE_DIR_NAME
    files = sorted(p.relative_to(legacy).as_posix() for p in legacy.rglob("*") if p.is_file())
    if not all(_is_local(rel) for rel in files) or (git and _tracked_anywhere(repo)):
        return None
    moves, merged, dropped, kept = [], [], [], []
    for rel in files:
        there = target / rel
        text = _merge_flat(legacy / rel, there) if rel in MERGED and there.is_file() else None
        if not there.exists():
            moves.append(rel)
        elif rel in DERIVED:
            dropped.append(rel)
        elif text is not None:
            merged.append((rel, text))
        else:
            kept.append(rel)
    return LocalFiles(tuple(moves), tuple(merged), tuple(dropped), tuple(kept))


def _prune(folder: Path) -> None:
    """Removes the empty folders under `folder`, deepest first, then `folder` itself when it is empty."""
    for sub in sorted((p for p in folder.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(sub.iterdir()):
            sub.rmdir()
    if not any(folder.iterdir()):
        folder.rmdir()


def _apply_local(repo: Path, local: LocalFiles) -> None:
    """Moves the local files; a rerun after a failure finds the rest and moves it."""
    legacy, target = repo / LEGACY_DIR, repo / STATE_DIR_NAME
    for rel in local.moves:
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        os.replace(legacy / rel, target / rel)
    for rel, text in local.merged:
        write_text_atomic(target / rel, text)
        (legacy / rel).unlink()
    for rel in local.dropped:
        (legacy / rel).unlink()
    _prune(legacy)


# --- plan, pull and apply ---

def plan(repo: Path) -> MigrationPlan:
    """What `apply` would do in `repo`, the root of the main worktree (or a folder outside git); writes nothing.

    With `.nod/` there already, only this machine's local files can move (`MigrationPlan.local`).
    `MigrateError` when there is nothing to migrate, the files are not committed or the manifest would
    not pass the check; `LoadError` when a file would not read after the migration; `ProtectedBranch`
    on `main` and `master`.
    """
    repo = Path(repo)
    legacy = repo / LEGACY_DIR
    git = _in_git(repo)
    if (repo / STATE_DIR_NAME).exists():
        if not legacy.is_dir():
            raise MigrateError(t("migrate.state_exists", path=f"{STATE_DIR_NAME}/"))
        local = _local_files(repo, git)
        if local is None:
            files = sorted(p.relative_to(repo).as_posix() for p in legacy.rglob("*") if p.is_file())
            raise MigrateError(t("migrate.both_exist", new=f"{STATE_DIR_NAME}/", old=f"{LEGACY_DIR}/",
                                 files=_listed(files)))
        return MigrationPlan(git, local=local)
    if not legacy.is_dir():
        raise MigrateError(t("migrate.no_legacy", path=f"{LEGACY_DIR}/"))
    gitignore, gitignore_lines = _gitignore(repo / GITIGNORE)
    tracked = origin = False
    if git:
        _check_branch(repo)
        tracked = _check_clean(repo, gitignore is not None)
        origin = GitSync(repo, LEGACY_DIR, remote=True).has_remote()
    rewrites = tuple(_rewrites(legacy))
    return MigrationPlan(git, tracked, rewrites, _manifest(legacy / harness.MANIFEST), gitignore,
                         gitignore_lines, origin)


def pull(repo: Path, current: MigrationPlan) -> MigrationPlan:
    """`pull --ff-only` before a migration that turns syncing on (`MigrationPlan.pulls`), then the plan again.

    The commit then lands on top of origin and its push goes through. `PullFailed` when the pull does
    not go through: nothing moved.
    """
    if not current.pulls:
        return current
    sync = GitSync(repo, LEGACY_DIR, remote=True)
    try:
        pulled = sync.pull_ff()
    except GitError as error:
        pulled, sync.last_error = False, str(error)
    if not pulled:
        raise PullFailed(t("migrate.pull_failed", error=sync.last_error))
    return plan(repo)


def _commit(repo: Path, plan: MigrationPlan) -> bool:
    """One commit: the older folder (when it was tracked), `.nod` without its local files, `.gitignore`."""
    local = [f"{STATE_DIR_NAME}/{name}" for name in LOCAL_FILES]
    staged = [STATE_DIR_NAME, *([GITIGNORE] if plan.gitignore is not None else [])]
    _git(repo, "add", "-A", "--", *staged)
    _git(repo, "reset", "-q", "--", *local)
    # `commit -- <path>` needs a path git knows: `.nod` holding local files only is not one.
    paths = [*([LEGACY_DIR] if plan.tracked else []), *(p for p in staged if _git(repo, "ls-files", "--", p))]
    if not paths or _run(repo, "diff", "--cached", "--quiet", "--", *paths).returncode == 0:
        return False
    _git(repo, "commit", "-q", "-m", SUBJECT, "--", *paths, *(f":!{path}" for path in local))
    return True


def _carry_out(repo: Path, plan: MigrationPlan, originals: list[tuple[Path, bytes]]) -> bool:
    """The move, the rewrites and the commit; `originals` collects the bytes `_undo` puts back."""
    target = repo / STATE_DIR_NAME
    if plan.tracked:
        _git(repo, "mv", LEGACY_DIR, STATE_DIR_NAME)
    else:
        os.replace(repo / LEGACY_DIR, target)
    writes = [(target / rewrite.path, rewrite.text) for rewrite in plan.rewrites]
    if plan.manifest.text is not None:
        writes.append((target / harness.MANIFEST, plan.manifest.text))
    if plan.gitignore is not None:
        writes.append((repo / GITIGNORE, plan.gitignore))
    for path, text in writes:
        originals.append((path, path.read_bytes()))
        write_text_atomic(path, text)
    return plan.git and _commit(repo, plan)


def _undo(repo: Path, plan: MigrationPlan, originals: list[tuple[Path, bytes]]) -> None:
    """Back to the state before `apply`: the file bytes, the folder name, the index of these paths."""
    for path, data in reversed(originals):
        path.write_bytes(data)
    legacy, target = repo / LEGACY_DIR, repo / STATE_DIR_NAME
    if target.is_dir() and not legacy.exists():
        os.replace(target, legacy)
    if plan.git:
        # `plan` refused a dirty index for these paths: HEAD is what they were before.
        _git(repo, "reset", "-q", "--", LEGACY_DIR, STATE_DIR_NAME, GITIGNORE)


def _reason(error: BaseException) -> str:
    return " ".join(str(error).split()) or type(error).__name__


def _push_after(repo: Path, remote: bool) -> None:
    """The push after the commit; a refusal is one line on stderr, as after any write."""
    sync = GitSync(repo, STATE_DIR_NAME, remote=remote)
    try:
        pushed = sync.push()
    except GitError as error:
        pushed, sync.last_error = False, str(error)
    if not pushed:
        print(t("context.push_failed", error=sync.last_error), file=sys.stderr)


def apply(repo: Path, plan: MigrationPlan) -> str | None:
    """Carries out `plan` in `repo`: the move, the rewrites, one commit, then a push with `[git] push = true`.

    Returns the sha of the commit; `None` outside git, when there was nothing to commit and when only
    local files moved. Any failure before the commit is in puts everything back and raises `MigrateError`.
    """
    repo = Path(repo)
    if plan.local is not None:
        _apply_local(repo, plan.local)
        return None
    originals: list[tuple[Path, bytes]] = []
    try:
        committed = _carry_out(repo, plan, originals)
    except BaseException as error:
        try:
            _undo(repo, plan, originals)
        except Exception as undo_error:
            raise MigrateError(t("migrate.undo_failed", error=_reason(error), undo=_reason(undo_error))) from error
        if not isinstance(error, Exception):
            raise
        raise MigrateError(t("migrate.undone", error=_reason(error))) from error
    if not committed:
        return None
    sha = _git(repo, "rev-parse", "HEAD").strip()
    _push_after(repo, plan.manifest.push)
    return sha
