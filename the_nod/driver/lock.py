"""The driver lock: `driver.lock` travels through git, the pid file stays local."""

import argparse
import os
import subprocess
from datetime import datetime
from typing import Callable

from the_nod import context
from the_nod.context import CliError, Context, Stale
from the_nod.gitsync import GitError, ProtectedBranch
from the_nod.i18n import t
from the_nod.paths import NO_WINDOW
from the_nod.store import Store

LOCK_TTL_SECONDS = 3600
HEARTBEAT_SECONDS = 1200


def lock_state(lock: dict | None, host: str, now: str) -> str:
    """`free`, `mine`, `abandoned` (someone else's and older than the TTL, or unreadable) or `foreign`."""
    if not lock:
        return "free"
    if lock.get("host") == host:
        return "mine"
    try:
        age = (datetime.fromisoformat(now) - datetime.fromisoformat(str(lock.get("at")))).total_seconds()
    except (ValueError, TypeError):
        return "abandoned"
    return "abandoned" if age > LOCK_TTL_SECONDS else "foreign"


def foreign_message(lock: dict) -> str:
    return t("driver.foreign", host=lock.get("host"), at=lock.get("at"))


last_refusal: str = ""
last_heartbeat: str = ""


def _refuse(reason: str) -> bool:
    global last_refusal
    last_refusal = reason
    return False


def _dirty_reason(ctx: Context) -> str:
    files = ctx.sync.dirty() if ctx.sync is not None else []
    return t("driver.dirty_tree", paths=", ".join(files)) if files else ""


def claim(ctx: Context, summary: str, fn: Callable[[], None]) -> bool:
    """The `fn` edit and the lock in one commit; when the push is refused, the tree goes back to the start.

    If `.nod/` already has unsaved edits (another `nod` is writing), it touches nothing
    and returns `False`: a rollback would erase that work. The refusal reason is in `last_refusal`.
    """
    global last_refusal
    before = None  # with git: HEAD before the write, `None` on a branch without commits yet
    if ctx.sync is not None:
        reason = _dirty_reason(ctx)
        if reason:
            return _refuse(reason)
        before = ctx.sync.head()
    try:
        pushed = ctx.write(summary, lambda: (fn(), ctx.store.write_lock(ctx.host, ctx.now)))
    except GitError:
        if ctx.sync is not None:
            ctx.sync.undo_last(before)
        raise
    if not pushed and ctx.sync is not None:
        ctx.sync.undo_last(before)
        return _refuse(t("driver.push_failed"))
    last_refusal = ""
    return True


def _heartbeat_refuse(reason: str) -> bool:
    global last_heartbeat
    last_heartbeat = reason
    return False


def heartbeat(ctx: Context) -> bool:
    """Updates `at` in our own lock after a fresh pull; `False` without an exception on any failure.

    It runs during the agent's command, so it keeps the `[git] push` mode of `ctx`: a manifest
    the agent changed does not make it talk to origin. The refusal reason is in `last_heartbeat`;
    `last_refusal` belongs to `claim` only.
    """
    global last_heartbeat
    try:
        ctx2 = context.open(argparse.Namespace(root=str(ctx.store.root)), remote=ctx.remote)
        if not ctx2.fresh:
            return _heartbeat_refuse(t("driver.heartbeat_stale"))
        if lock_state(ctx2.store.lock(), ctx2.host, ctx2.now) != "mine":
            return _heartbeat_refuse(t("driver.heartbeat_foreign"))
        reason = _dirty_reason(ctx2)
        if reason:
            return _heartbeat_refuse(reason)
        before = ctx2.sync.head() if ctx2.sync is not None else None
        pushed = ctx2.write("driver heartbeat", lambda: ctx2.store.write_lock(ctx2.host, ctx2.now))
        if not pushed:
            if ctx2.sync is not None:
                ctx2.sync.undo_last(before)
            return _heartbeat_refuse(t("driver.push_failed"))
        last_heartbeat = ""
        return True
    except (Stale, GitError, ProtectedBranch, CliError) as err:
        return _heartbeat_refuse(f"{err}")


def _alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True,
                             creationflags=NO_WINDOW,
                             text=True, encoding="utf-8", errors="replace").stdout
        return str(pid) in out.split()
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_pid(path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _create_exclusive(path) -> bool:
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    return True


def process_lock(store: Store) -> int | None:
    """A live pid of someone else gives that pid; otherwise takes the pid file with our pid and returns `None`.

    `-1` means the file vanished in the middle of a race and could not be taken: count it as busy.
    """
    path = store.root / "driver" / "pid"
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        for _ in range(2):
            if _create_exclusive(path):
                break
            pid = _read_pid(path)
            if pid == os.getpid():
                return None
            if pid is not None and _alive(pid):
                return pid
            path.unlink(missing_ok=True)
        owner = _read_pid(path)
        if owner == os.getpid():
            return None
        if owner is not None:
            return owner
    return -1


def release(store: Store) -> None:
    path = store.root / "driver" / "pid"
    try:
        if int(path.read_text(encoding="utf-8").strip()) == os.getpid():
            path.unlink()
    except (OSError, ValueError):
        pass
