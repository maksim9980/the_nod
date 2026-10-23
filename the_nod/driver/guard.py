"""The guard of the agent command: the empty hooks folder, the `.nod/` state, the manifest.

Before the command the driver takes references; after it, it compares and restores what the agent touched.
The caller (`apply_brief.tampered`) writes the owner decision through a fresh context.

- The hooks folder lies under `.git` (the common folder, for a worktree too): the agent may not edit `.git`,
  and a file in the `core.hooksPath` folder would run as a hook.
- The state: uncommitted `.nod/` edits (except `driver/` and the local files) after the command
  are agent edits that bypass `nod`; they roll back to HEAD. Committed edits are not checked this way:
  the agent writes its own records lawfully (`nod run progress`, `nod decision ask`, `nod card add`),
  and the owner writes from their own `nod` during the command; git cannot tell those from an agent commit.
- The manifest: the reference is the origin version (`[git] push = true` and origin exists),
  otherwise the sha256 before the command; with push off nothing is fetched.
  The origin reference is taken before the command: a heartbeat during the command may push an agent commit.
"""

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from the_nod.context import Context
from the_nod.driver.log import Log
from the_nod.gitsync import GitError
from the_nod.i18n import t
from the_nod.paths import NO_WINDOW
from the_nod.store import write_text_atomic

HOOKS_DIR_NAME = "nod-no-hooks"
MANIFEST_FILE = "harness.toml"

# Names of the findings: identifiers in the `changed` lists, shown to people through `label`.
# Hook files join those lists under their own names, so a name here is not a likely file name.
HOOKS = "hooks folder"
STATE = ".nod state"
STATE_FAILED = ".nod state (not restored)"
MANIFEST_REMOTE = "harness.toml (origin)"
MANIFEST_LOCAL = "harness.toml"
# A change of the git config: not restored here, named in the owner text with the changed hooks.
GIT_CONFIG = "git config"
# The owner text of each restored finding.
TEXT_KEYS = {
    HOOKS: "driver.guard_hooks",
    STATE: "driver.guard_state",
    MANIFEST_REMOTE: "driver.guard_manifest_origin",
    MANIFEST_LOCAL: "driver.guard_manifest_local",
}
_LABEL_KEYS = {HOOKS: "driver.name_hooks", STATE: "driver.name_state", STATE_FAILED: "driver.name_state_failed",
               GIT_CONFIG: "driver.name_git_config"}
SUMMARIES = ((STATE, "driver restore state"), (MANIFEST_REMOTE, "driver restore harness.toml"),
             (MANIFEST_LOCAL, "driver restore harness.toml"))
NAMES = frozenset(TEXT_KEYS) | {STATE_FAILED}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    except OSError:
        return None


# --- the empty hooks folder ---

def hooks_dir(root: Path) -> Path:
    """`<common .git>/nod-no-hooks`; the common folder serves a linked worktree too."""
    done = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    common = Path(done.stdout.strip()) if done is not None and done.returncode == 0 and done.stdout.strip() \
        else Path(root) / ".git"
    return common / HOOKS_DIR_NAME


def is_link(path: Path) -> bool:
    """A symlink or a Windows junction: removed as a link, never followed (`remove_path`)."""
    return path.is_symlink() or os.path.isjunction(path)


def _remove_link(path: Path) -> None:
    """A link or a junction: only the link itself, without going inside."""
    try:
        os.rmdir(path)
    except OSError:
        os.unlink(path)


def remove_path(path: Path) -> None:
    """A file, a link or a folder; links and junctions are not followed."""
    if is_link(path):
        _remove_link(path)
    elif path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def clear_hooks(folder: Path) -> bool:
    """`True` if the folder was replaced or held something; it is then already empty and real.

    A folder replaced by a link or a junction is removed as a link: the removal does not follow it outside.
    """
    if is_link(folder) or (folder.exists() and not folder.is_dir()):
        remove_path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        return True
    if not folder.is_dir():
        return False
    entries = list(folder.iterdir())
    for entry in entries:
        remove_path(entry)
    return bool(entries)


# --- the state ---

def _dirty_paths(ctx: Context) -> list[str]:
    """The same dirty tree check as the lock has (`GitSync.dirty`): the guard and `claim` agree."""
    return ctx.sync.dirty()


def _rollback(root: Path, paths: list[str]) -> list[str]:
    """Rolls the paths back to HEAD; what did not roll back is returned (by git codes and file errors).

    If git did not start for `cat-file`, it is unknown whether the file is tracked: it is not removed
    and goes into the answer.
    """
    failed = []
    _git(root, "reset", "-q", "HEAD", "--", *paths)  # the code does not matter: a second check decides
    for rel in paths:
        tracked = _git(root, "cat-file", "-e", f"HEAD:{rel}")
        if tracked is None:
            failed.append(rel)
            continue
        if tracked.returncode == 0:
            done = _git(root, "checkout", "HEAD", "--", rel)
            ok = done is not None and done.returncode == 0
        else:
            try:
                remove_path(root / rel)
                ok = True
            except OSError:
                ok = False
        if not ok:
            failed.append(rel)
    return failed


def restore_state(ctx: Context, log: Log) -> str:
    """`STATE` if `.nod/` had uncommitted edits and they rolled back to HEAD;
    `STATE_FAILED` if the tree is still dirty after the rollback; empty if there were no edits.

    With `STATE_FAILED` nothing may be written: `ctx.write` would run `add -A .nod` and commit
    the agent edits. The next `claim` refuses on the dirty tree.
    """
    if ctx.sync is None:
        return ""
    paths = _dirty_paths(ctx)
    if not paths:
        return ""
    failed = _rollback(ctx.sync.repo_root, paths)
    left = sorted({*_dirty_paths(ctx), *(p for p in failed if (ctx.sync.repo_root / p).exists())})
    if left:
        log.error(t("driver.state_not_restored", paths=", ".join(left)))
        return STATE_FAILED
    if failed:
        log.warn(t("driver.rollback_error", paths=", ".join(failed)))
    return STATE


# --- the manifest ---

@dataclass(frozen=True)
class Reference:
    """The manifest reference: the origin text (`None` if the fetch failed) and the sha and text before the command."""

    remote: str | None
    sha: str
    text: str | None


def _read(ctx: Context) -> str | None:
    try:
        return (ctx.store.root / MANIFEST_FILE).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def manifest_sha(ctx: Context) -> str:
    """The sha256 of the manifest file; empty without the file."""
    try:
        return hashlib.sha256((ctx.store.root / MANIFEST_FILE).read_bytes()).hexdigest()
    except OSError:
        return ""


def _remote(ctx: Context) -> str | None:
    if ctx.sync is None:
        return None
    try:
        return ctx.sync.remote_file(f"{ctx.sync.state_rel}/{MANIFEST_FILE}")
    except GitError:
        return None


def snapshot(ctx: Context) -> Reference:
    return Reference(remote=_remote(ctx), sha=manifest_sha(ctx), text=_read(ctx))


def _same(a: str | None, b: str | None) -> bool:
    def norm(s: str | None) -> str | None:
        return None if s is None else s.replace("\r\n", "\n")
    return norm(a) == norm(b)


def restore_manifest(ctx: Context, ref: Reference) -> str:
    """The finding name (`MANIFEST_REMOTE`/`MANIFEST_LOCAL`) or empty; the file is already back at the reference."""
    path = ctx.store.root / MANIFEST_FILE
    if ref.remote is not None:
        if _same(_read(ctx), ref.remote):
            return ""
        write_text_atomic(path, ref.remote)
        return MANIFEST_REMOTE
    if manifest_sha(ctx) == ref.sha:
        return ""
    if ref.text is not None:
        write_text_atomic(path, ref.text)
    return MANIFEST_LOCAL


# --- all together ---

def after(ctx: Context, folder: Path, ref: Reference, log: Log) -> list[str]:
    """The check after the command: the finding names; everything touched is already restored on disk.

    The checks are independent and fail closed: a git or file error inside a check is a finding too
    (an ERROR in the log), and the other checks still run. The state is checked before the manifest:
    an uncommitted manifest edit rolls back to HEAD.
    """
    manifest_name = MANIFEST_REMOTE if ref.remote is not None else MANIFEST_LOCAL
    checks = ((HOOKS, lambda: HOOKS if clear_hooks(folder) else ""),
              (STATE, lambda: restore_state(ctx, log)),
              (manifest_name, lambda: restore_manifest(ctx, ref)))
    found = []
    for name, check in checks:
        try:
            hit = check()
        except (GitError, OSError) as err:
            log.error(t("driver.check_failed", name=label(name), error=err))
            # The state is not checked, so it is not restored: every write is blocked.
            hit = STATE_FAILED if name == STATE else name
        if hit:
            found.append(hit)
    return found


def label(name: str) -> str:
    """How a finding is named in the log and in owner texts; a hook file keeps its own name."""
    key = _LABEL_KEYS.get(name)
    return t(key) if key else name


def owner_text(changed: list[str]) -> str:
    return "; ".join(t(TEXT_KEYS[n]) for n in changed if n in TEXT_KEYS)


def summary(changed: list[str], card_id: str) -> str:
    """The subject of the restore commit; empty when the commit has nothing to restore."""
    return next((f"{text} {card_id}" for name, text in SUMMARIES if name in changed), "")
