"""Running the agent command: the prompt on stdin, the hang check, the heartbeat.

`shell=True` is on purpose: the manifest gives a shell line; the driver decides what goes into it
(card titles do not).
"""

import codecs
import hashlib
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from the_nod.paths import NO_WINDOW

GIT_CONFIG_PARAMETERS = "GIT_CONFIG_PARAMETERS"
TAIL_LIMIT = 64 * 1024  # the stdout/stderr tail (in characters) kept in Outcome
JOIN_WAIT = 1.0  # how long to wait for the pipe readers after the process ends, seconds
POLL = 0.25  # the process wait step, seconds
KILL_WAIT = 5  # how long to wait for the process after kill, seconds
# The one time scale of the module is time.time(): activity() returns a file mtime, which is epoch time.


@dataclass(frozen=True)
class Outcome:
    status: str  # "exit" | "stuck" | "spawn-error"
    code: int | None
    stdout: str
    stderr: str
    seconds: int


class _Tail:
    """An output buffer: keeps the last TAIL_LIMIT characters and the time of the last chunk."""

    def __init__(self, clock: Callable[[], float]):
        self._lock = threading.Lock()
        self._clock = clock
        self.text = ""
        self.last = 0.0

    def add(self, chunk: str) -> None:
        with self._lock:
            self.text = (self.text + chunk)[-TAIL_LIMIT:]
            self.last = self._clock()

    def note(self, line: str) -> None:
        """A service line that does not update the time of the last output."""
        with self._lock:
            self.text = (self.text + line)[-TAIL_LIMIT:]

    def value(self) -> str:
        with self._lock:
            return self.text


def git_env(hooks_dir: Path) -> dict[str, str]:
    """An environment that turns off the git hooks of `.git/hooks`: `core.hooksPath` points to an empty folder.

    A single quote in the path is escaped as `'\\''`; an existing `GIT_CONFIG_PARAMETERS`
    is extended after a space.
    """
    hooks_dir.mkdir(parents=True, exist_ok=True)
    path = hooks_dir.as_posix().replace("'", "'\\''")
    own = f"'core.hooksPath={path}'"
    existing = os.environ.get(GIT_CONFIG_PARAMETERS, "").strip()
    return {GIT_CONFIG_PARAMETERS: f"{existing} {own}" if existing else own}


def _git(root: Path, *args: str) -> str | None:
    """The stdout of a git command in `root`; any error gives None."""
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=True, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hooks_folder(root: Path) -> Path:
    """The hooks folder: `<git-common-dir>/hooks`. `core.hooksPath` of the repo config is ignored:
    the agent could have set it. A git error gives `<root>/.git/hooks`."""
    line = (_git(root, "rev-parse", "--git-common-dir") or "").strip()
    return (root / line / "hooks") if line else root / ".git" / "hooks"


def hooks_snapshot(folder: Path) -> dict[str, str]:
    """Name to sha256 of the content of the hooks folder files, `.sample` excluded (an mtime can be faked).

    `folder` is computed once before the agent command (`hooks_folder`). No folder gives an empty dict.
    """
    if not folder.is_dir():
        return {}
    items = [p for p in folder.iterdir() if p.is_file() and not p.name.endswith(".sample")]
    return {p.name: _sha256(p.read_bytes()) for p in sorted(items, key=lambda p: p.name)}


def config_snapshot(root: Path) -> str | None:
    """The sha256 of the `git config --list --show-origin` output (git expands include/includeIf itself).

    A git error gives the sha256 of the `git rev-parse --git-path config` file; otherwise None.
    """
    listing = _git(root, "config", "--list", "--show-origin")
    if listing is not None:
        return _sha256(listing.encode("utf-8"))
    line = (_git(root, "rev-parse", "--git-path", "config") or "").strip()
    path = root / line if line else None
    return _sha256(path.read_bytes()) if path is not None and path.is_file() else None


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill the process with its children: `taskkill /T` on Windows, the whole process group on POSIX.

    On POSIX `run_command` starts the command in a new session, so its group id is its pid.
    """
    try:
        if sys.platform == "win32":
            try:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                               creationflags=NO_WINDOW)
            except OSError:
                proc.kill()
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:  # the group is gone already, or the process leads none
                proc.kill()
        proc.wait(timeout=KILL_WAIT)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _drain(stream, tail: _Tail) -> None:
    """Read the pipe in chunks as they come (read1 does not wait for a full buffer)."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    try:
        while chunk := stream.read1(4096):
            text = decoder.decode(chunk)
            if text:
                tail.add(text)
        tail.add(decoder.decode(b"", final=True))
    except (OSError, ValueError):
        pass
    finally:
        stream.close()  # the reader closes its pipe; a close() from outside would block on the read lock


def _feed(stream, text: str) -> None:
    try:
        stream.write(text.encode("utf-8"))
    except OSError:
        pass  # the process closed stdin before it read the whole prompt
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _safe_activity(activity: Callable[[], float]) -> float:
    try:
        return activity()
    except Exception:  # a failed activity read counts as no activity
        return 0.0


def _beat(tick: Callable[[], None], err: _Tail) -> None:
    try:
        tick()
    except Exception as exc:  # the heartbeat must not break the wait
        err.note(f"\nheartbeat: {exc}\n")


def _wait(proc, start, out, err, activity, stuck_after, tick, tick_every) -> str:
    next_tick = start + tick_every
    try:
        while True:
            try:
                proc.wait(timeout=POLL)
                return "exit"
            except subprocess.TimeoutExpired:
                pass
            now = time.time()
            if now - max(start, out.last, err.last, _safe_activity(activity)) > stuck_after:
                kill_tree(proc)
                return "stuck"
            if tick is not None and now >= next_tick:
                _beat(tick, err)
                next_tick += tick_every
    finally:
        if proc.poll() is None:  # interrupted (KeyboardInterrupt and the like): the agent does not stay alive
            kill_tree(proc)


def run_command(
    command: str,
    *,
    cwd: Path,
    stdin: str,
    env: dict[str, str],
    activity: Callable[[], float],
    stuck_after: float,
    tick: Callable[[], None] | None = None,
    tick_every: float = 1200.0,
    hooks_dir: Path | None = None,
) -> Outcome:
    """Run the command with `stdin`; return the outcome. A hang is silence longer than `stuck_after`."""
    child_env = {**os.environ, **env}
    if hooks_dir is not None:
        child_env.update(git_env(hooks_dir))
    windows = sys.platform == "win32"
    flags = (subprocess.CREATE_NEW_PROCESS_GROUP | NO_WINDOW) if windows else 0
    start = time.time()
    try:
        proc = subprocess.Popen(
            command, shell=True, cwd=cwd, env=child_env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags,
            start_new_session=not windows)  # POSIX: its own process group, which kill_tree kills whole
    except OSError as err:
        return Outcome("spawn-error", None, "", str(err), 0)
    out, err = _Tail(time.time), _Tail(time.time)
    threads = [
        threading.Thread(target=_drain, args=(proc.stdout, out), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, err), daemon=True),
        threading.Thread(target=_feed, args=(proc.stdin, stdin), daemon=True),
    ]
    for t in threads:
        t.start()
    status = _wait(proc, start, out, err, activity, stuck_after, tick, tick_every)
    for t in threads:
        t.join(timeout=JOIN_WAIT)
    code = proc.returncode if status == "exit" else None
    return Outcome(status, code, out.value(), err.value(), round(time.time() - start))
