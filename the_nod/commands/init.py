"""`nod init`: creates `.nod/` at the root of the repo's main worktree."""

import argparse
from pathlib import Path

from the_nod import context, i18n, migrate
from the_nod.gitsync import GitSync, ProtectedBranch
from the_nod.i18n import t
from the_nod.paths import STATE_DIR_NAME, NotARepo, main_worktree_root
from the_nod.store import Store, write_text_atomic

IGNORED = (f"{STATE_DIR_NAME}/state.json", f"{STATE_DIR_NAME}/seen.toml",
           f"{STATE_DIR_NAME}/driver.log", f"{STATE_DIR_NAME}/driver.log.1",
           f"{STATE_DIR_NAME}/driver/")


def add_parser(sub) -> None:
    parser = sub.add_parser("init", help=t("help.init"))
    parser.set_defaults(run=run)


def harness_template() -> str:
    """The commented default manifest in the current language, with `lang` set to it."""
    return t("init.harness_template", lang=i18n.current())


def _state_dir(root: str | None) -> Path:
    """Where the state goes: from `--root`, else the repo's main worktree from cwd."""
    if root is None:
        return main_worktree_root(Path.cwd()) / STATE_DIR_NAME
    given = Path(root).absolute()
    return given if given.name == STATE_DIR_NAME else given / STATE_DIR_NAME


def _check_branch(state_dir: Path) -> None:
    """In a git repo the state is committed on a work branch: a protected branch or a detached HEAD
    is refused before anything is created."""
    try:
        root = main_worktree_root(state_dir.parent)
    except NotARepo:
        return
    sync = GitSync(root, remote=False)
    branch = sync.branch()  # GitError on a detached HEAD
    if sync.is_protected(branch):
        raise ProtectedBranch(t("init.protected_branch", branch=branch))


def _update_gitignore(repo: Path) -> bool:
    """Appends the missing lines; `True` if the file changed. It is outside `.nod`: `nod` does not commit it."""
    path = repo / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    present = set(text.splitlines())
    missing = [line for line in IGNORED if line not in present]
    if not missing:
        return False
    prefix = "" if not text or text.endswith("\n") else "\n"
    write_text_atomic(path, text + prefix + "\n".join(missing) + "\n")
    return True


def _create_files(store: Store) -> None:
    harness = store.root / "harness.toml"
    if not harness.exists():
        write_text_atomic(harness, harness_template())
    if not (store.root / "order.md").exists():
        store.set_order([])


def _check_legacy(state_dir: Path) -> None:
    """Next to the older version's folder a fresh state would hide it: `nod migrate` moves it instead."""
    if not state_dir.is_dir() and (state_dir.parent / migrate.LEGACY_DIR).is_dir():
        raise context.CliError(t("migrate.legacy_found", path=f"{migrate.LEGACY_DIR}/"))


def run(args) -> int:
    context.refuse_agent()
    state_dir = _state_dir(args.root)
    _check_legacy(state_dir)
    _check_branch(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    ignored = _update_gitignore(state_dir.parent)
    ctx = context.open(argparse.Namespace(root=str(state_dir)))
    ctx.write("init", lambda: _create_files(ctx.store))
    lines = [t("init.created", dir=STATE_DIR_NAME, parent=state_dir.parent),
             *([t("init.gitignore_uncommitted")] if ignored else [])]
    context.emit(args, {"created": str(state_dir)}, "\n".join(lines))
    return 0
