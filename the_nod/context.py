"""Command context: where the state is, whether it is fresh, and the single write path."""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from the_nod import frontmatter, harness, i18n, migrate, snapshot
from the_nod.gitsync import GitError, GitSync, ProtectedBranch
from the_nod.i18n import t
from the_nod.model import now_iso
from the_nod.paths import (STATE_DIR_NAME, NotARepo, find_state_dir,
                           host_name, main_worktree_root)
from the_nod.store import Store, write_text_atomic

STALE_KEY = "stale_since"
# The driver sets it for the agent's command: owner answers and closing cards are not for the agent.
AGENT_ENV = "NOD_AGENT"


class CliError(RuntimeError):
    """A usage error: the message is shown as is."""


class Stale(RuntimeError):
    """The state is not fresh: no writes until a successful pull."""


def emit(args, data: dict, text: str = "") -> None:
    """Command output: JSON with `--json`, otherwise the text when it is not empty."""
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif text:
        print(text)


def under_agent() -> bool:
    """Whether this process is a command of the driver's agent (`NOD_AGENT`)."""
    return bool(os.environ.get(AGENT_ENV))


def refuse_agent() -> None:
    """`CliError` under the driver's agent: it cannot answer for the owner or close cards."""
    if under_agent():
        raise CliError(t("context.agent_refused"))


def use_lang(state_dir: Path) -> None:
    """Switches to the language of the state in `state_dir`; NOD_LANG wins over the manifest."""
    i18n.use(i18n.resolve(harness.read_lang(state_dir)))


@dataclass
class Context:
    store: Store
    sync: GitSync | None
    host: str
    now: str
    fresh: bool
    stale_since: str | None

    @property
    def remote(self) -> bool | None:
        """Whether this context talks to origin (`[git] push`); `None` outside git."""
        return None if self.sync is None else self.sync.remote

    def write(self, summary: str, fn: Callable[[], None]) -> bool:
        """The single write path: fn, a fresh state.json, commit, push (with `[git] push = true`).

        `True` if the push went through or there is no remote to push to; `False` if the push was refused.
        """
        # The branch is checked first: on a detached HEAD the pull fails too, but freshness is not the point.
        branch = self.sync.branch() if self.sync is not None else None
        if not self.fresh:
            raise Stale(t("context.stale", since=self.stale_since))
        if branch is not None and self.sync.is_protected(branch):
            raise ProtectedBranch(t("git.protected_state", branch=branch))
        fn()
        state = snapshot.build(self.store, now=now_iso(), host=self.host, since=None,
                               fresh=self.fresh, stale_since=self.stale_since)
        snapshot.write(self.store, state)
        if self.sync is None:
            return True
        self.sync.commit(summary)
        if not self.sync.push():
            print(t("context.push_failed", error=self.sync.last_error), file=sys.stderr)
            return False
        return True


def _check_main_tree(state_dir: Path) -> None:
    """State in a run's worktree would miss the commit: GitSync writes from the main tree."""
    try:
        main_root = main_worktree_root(state_dir.parent)
    except NotARepo:
        return
    if state_dir.parent.resolve() != main_root:
        raise CliError(t("context.not_main_tree", path=main_root / STATE_DIR_NAME))


def _no_state(places: list[Path]) -> CliError:
    """No `.nod`: a hint to migrate when one of `places` is, or holds, the older version's folder."""
    legacy = any((place.name == migrate.LEGACY_DIR and place.is_dir()) or (place / migrate.LEGACY_DIR).is_dir()
                 for place in places)
    return CliError(t("migrate.legacy_found", path=f"{migrate.LEGACY_DIR}/") if legacy else t("context.no_state"))


def resolve_state_dir(root: str | None, cwd: Path) -> Path:
    """The `.nod` folder: from `--root` (as an absolute path), else in the repo's main tree from cwd."""
    if root is not None:
        given = Path(root).absolute()
        candidate = given if given.name == STATE_DIR_NAME else given / STATE_DIR_NAME
        _check_main_tree(candidate)
        places = [given, candidate.parent]
    else:
        try:
            candidate = main_worktree_root(cwd) / STATE_DIR_NAME
            places = [candidate.parent]
        except NotARepo:
            candidate = find_state_dir(cwd)
            start = Path(cwd).absolute()
            places = [start, *start.parents]
    if candidate is None or not candidate.is_dir():
        raise _no_state(places)
    return candidate


def _git_sync(state_dir: Path, remote: bool | None) -> GitSync | None:
    """Git of the state; it talks to origin only with `[git] push = true` in the manifest.

    A `remote` from the caller wins over the manifest (see `open`).
    """
    try:
        root = main_worktree_root(state_dir.parent)
    except NotARepo:
        return None
    push = harness.read_push(state_dir) if remote is None else remote
    return GitSync(root, state_dir.name, remote=push)


def _set_stale(store: Store, value: str | None) -> None:
    """Writes or removes the `stale_since` key in seen.toml, leaving the rest alone."""
    path = store.root / "seen.toml"
    if value is None and not path.exists():
        return
    data = {k: v for k, v in store.seen().items() if k != STALE_KEY}
    if value is not None:
        data[STALE_KEY] = value
    write_text_atomic(path, frontmatter.toml_flat(data))


def open(args, *, sync: bool = True, remote: bool | None = None) -> Context:
    """Finds the state, switches to its language, pulls with `sync` and decides whether it is fresh.

    `remote` (`Context.remote` of an earlier context) keeps that mode instead of reading `[git] push`:
    the driver reopens the state while an agent's command may have touched the manifest.
    """
    store = Store(resolve_state_dir(args.root, Path.cwd()))
    use_lang(store.root)
    git = _git_sync(store.root, remote)
    host, now = host_name(), now_iso()
    if git is None:
        return Context(store, None, host, now, True, None)
    if not sync:
        stale = store.seen().get(STALE_KEY)
        return Context(store, git, host, now, stale is None, stale)
    try:
        pulled = git.pull_ff()
    except GitError as err:
        git.last_error = str(err)
        pulled = False
    if pulled:
        _set_stale(store, None)
        return Context(store, git, host, now, True, None)
    stale = store.seen().get(STALE_KEY) or now
    _set_stale(store, stale)
    return Context(store, git, host, now, False, stale)
