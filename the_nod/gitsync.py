"""State sync through git: commit `.nod/`, and with `[git] push = true` also push and pull --ff-only."""

import subprocess
from pathlib import Path

from the_nod.i18n import t
from the_nod.paths import NO_WINDOW

PROTECTED = ("main", "master")
REMOTE = "origin"
DETACHED = 1  # exit code of `git symbolic-ref -q HEAD` outside a branch
NO_OBJECT = 1  # exit code of `git rev-parse -q --verify`: no such commit (a branch without commits)
NO_MATCHING_REF = 2  # exit code of `git ls-remote --exit-code`: no such branch
# Local files and folders: never committed, each machine has its own.
LOCAL_FILES = ("state.json", "seen.toml", "driver.log", "driver.log.1", "driver")


class ProtectedBranch(RuntimeError):
    """Writing the state on a protected branch is refused."""


class GitError(RuntimeError):
    """Git failed where going on is not possible."""


class GitSync:
    """Git of the state. With `remote=False` (the default manifest) nothing here talks to a remote."""

    def __init__(self, repo_root: Path, state_rel: str = ".nod", *, remote: bool = True):
        self.repo_root = Path(repo_root)
        self.state_rel = state_rel
        self.remote = remote
        self.last_error = ""

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                ["git", *args], cwd=self.repo_root, capture_output=True,
                text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW, stdin=subprocess.DEVNULL,
            )
        except OSError as err:
            raise GitError(t("git.not_found")) from err

    def _must(self, *args: str) -> str:
        result = self._git(*args)
        if result.returncode != 0:
            raise GitError(f"git {args[0]}: {result.stderr.strip()}")
        return result.stdout.strip()

    def _pathspec(self) -> list[str]:
        return [self.state_rel, *(f":!{self.state_rel}/{name}" for name in LOCAL_FILES)]

    def branch(self) -> str:
        """The current branch, also one without commits yet; on a detached HEAD the commit would be lost."""
        result = self._git("symbolic-ref", "--short", "-q", "HEAD")
        if result.returncode == DETACHED:
            raise GitError(t("git.detached"))
        if result.returncode != 0:
            raise GitError(f"git symbolic-ref: {result.stderr.strip()}")
        return result.stdout.strip()

    def is_protected(self, branch: str) -> bool:
        return branch in PROTECTED

    def has_remote(self) -> bool:
        """`origin` exists and the manifest allows talking to it; push, pull and fetch depend on it."""
        if not self.remote:
            return False
        return REMOTE in self._must("remote").split()

    def commit(self, summary: str) -> str | None:
        """Commits `.nod/` only; the sha, or `None` when there is nothing to commit."""
        branch = self.branch()
        if self.is_protected(branch):
            raise ProtectedBranch(t("git.protected_state", branch=branch))
        if not (self.repo_root / self.state_rel).is_dir():
            return None
        # An exclusion in the `add` pathspec does not help: git fails on an ignored file named explicitly.
        self._must("add", "-A", "--", self.state_rel)
        self._must("reset", "-q", "--", *(f"{self.state_rel}/{name}" for name in LOCAL_FILES))
        if self._git("diff", "--cached", "--quiet", "--", self.state_rel).returncode == 0:
            return None
        self._must("commit", "-m", f"state: {summary}", "--", *self._pathspec())
        return self._must("rev-parse", "HEAD")

    def dirty(self) -> list[str]:
        """Changed, new and ignored paths of `.nod/`, except the local files.

        One check for all: the lock (`claim`, `heartbeat`) and the guard of the agent's command.
        `--ignored=matching`: a forged card behind someone's `.gitignore` is dirt too.
        """
        entries = self._status("--ignored=matching", "--", *self._pathspec())
        paths = [p for _, path, origin in entries for p in (path, origin) if p]
        return [path for path in paths if not self._local(path)]

    def _status(self, *args: str) -> list[tuple[str, str, str]]:
        """Records of `status --porcelain -z -uall`: the XY code, the path and the rename source (or empty)."""
        result = self._git("-c", "core.quotePath=false", "status", "--porcelain", "-z", "-uall", *args)
        if result.returncode != 0:
            raise GitError(f"git status: {result.stderr.strip()}")
        records, entries = result.stdout.split("\0"), []
        i = 0
        while i < len(records):
            record = records[i]
            i += 1
            if len(record) < 4:
                continue
            origin = ""
            if record[0] in "RC" and i < len(records):  # the rename source comes next
                origin = records[i]
                i += 1
            entries.append((record[:2], record[3:].rstrip("/"), origin))
        return entries

    def changed(self, rel: str) -> list[str]:
        """New and changed files under `rel` (from the repo root); deleted ones do not count."""
        return [path for code, path, _ in self._status("--", rel) if "D" not in code]

    def commit_paths(self, paths: list[str], message: str) -> str | None:
        """Commits `paths` only (from the repo root); the sha, or `None` when there is nothing to commit."""
        branch = self.branch()
        if self.is_protected(branch):
            raise ProtectedBranch(t("git.protected_commit", branch=branch))
        self._must("add", "--", *paths)
        if self._git("diff", "--cached", "--quiet", "--", *paths).returncode == 0:
            return None
        self._must("commit", "-m", message, "--", *paths)
        return self._must("rev-parse", "HEAD")

    def _local(self, path: str) -> bool:
        """A local path: `--ignored` shows the ignored `driver/` folder as a whole, past the `:!` exclusion."""
        rel = self.state_rel
        return any(path == f"{rel}/{name}" or path.startswith(f"{rel}/{name}/") for name in LOCAL_FILES)

    def _commit_sha(self, rev: str) -> str | None:
        """The sha of `rev`, or `None` when there is no such commit."""
        result = self._git("rev-parse", "-q", "--verify", f"{rev}^{{commit}}")
        if result.returncode == NO_OBJECT:
            return None
        if result.returncode != 0:
            raise GitError(f"git rev-parse: {result.stderr.strip()}")
        return result.stdout.strip()

    def head(self) -> str | None:
        """The sha of HEAD; `None` on a branch without commits yet."""
        return self._commit_sha("HEAD")

    def undo_last(self, sha: str | None) -> None:
        """Moves HEAD and the index back to `sha`; unrelated edits in the tree stay.

        `sha` is `None` when `head()` was taken before the first commit: the root commit made since
        is dropped, its files leave the index and the tree, and the branch has no commits again.
        Like `reset --keep`, a file edited after that commit stops it. Nothing committed: nothing to do.
        """
        if sha is not None:
            self._must("reset", "--keep", sha)
            return
        head = self.head()
        if head is None:
            return
        if self._commit_sha("HEAD^") is not None:
            raise GitError(t("git.undo_not_root", sha=head))
        files = [f for f in self._must("ls-tree", "-r", "-z", "--name-only", "HEAD").split("\0") if f]
        # Only a root commit of the state is ours to drop: one that holds other files is the owner's.
        foreign = [f for f in files if not f.startswith(f"{self.state_rel}/")]
        if foreign:
            raise GitError(t("git.undo_foreign", sha=head, path=foreign[0], state=self.state_rel))
        if files:
            self._must("rm", "-q", "--", *files)
        self._must("update-ref", "-d", "HEAD", head)

    def remote_file(self, path: str) -> str | None:
        """File `path` (from the repo root) in `origin/<branch>` after a fetch; `None` without origin, branch or file."""
        if not self.has_remote():
            return None
        branch = self.branch()
        if self._git("fetch", "-q", REMOTE, branch).returncode != 0:
            return None
        shown = self._git("show", f"{REMOTE}/{branch}:{path}")
        return shown.stdout if shown.returncode == 0 else None

    def log_subjects(self, since: str) -> list[str]:
        """Subjects of state commits since `since`, newest first; `[]` if git fails."""
        result = self._git("log", f"--since={since}", "--format=%s", "--", self.state_rel)
        return result.stdout.splitlines() if result.returncode == 0 else []

    def _remote_call(self, *args: str) -> bool:
        if not self.has_remote():
            return True
        result = self._git(*args)
        self.last_error = result.stderr.strip() if result.returncode != 0 else ""
        return result.returncode == 0

    def push(self) -> bool:
        return self._remote_call("push", REMOTE, f"HEAD:{self.branch()}")

    def pull_ff(self) -> bool:
        """Pull --ff-only; when origin has no such branch yet there is nothing to pull, the push creates it."""
        if not self.has_remote():
            return True
        branch = self.branch()
        probe = self._git("ls-remote", "--exit-code", "--heads", REMOTE, branch)
        if probe.returncode == NO_MATCHING_REF:
            self.last_error = ""
            return True
        if probe.returncode != 0:
            self.last_error = probe.stderr.strip()
            return False
        return self._remote_call("pull", "--ff-only", REMOTE, branch)
