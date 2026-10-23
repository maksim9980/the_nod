"""The driver loop: a pass at once, then on a state change, after work and by the timer."""

import time
from pathlib import Path

from the_nod import context
from the_nod.driver import lock, once
from the_nod.driver.log import Log
from the_nod.i18n import t
from the_nod.store import Store

POLL_SECONDS = 30.0
PULL_EVERY_SECONDS = 300.0
SLEEP_STEP = 0.1
QUIET = ("idle", "foreign", "stale", "busy", "error")
REPEATING_QUIET = ("foreign", "stale", "busy")
WATCHED_DIRS = ("cards", "decisions", "runs")
WATCHED_FILES = ("order.md", "harness.toml")


def _mtime(path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def state_mtime(store: Store) -> float:
    """The largest mtime of the state files; a missing one counts as 0.0."""
    times = [_mtime(store.root / name) for name in WATCHED_FILES]
    for folder in WATCHED_DIRS:
        try:
            times.extend(_mtime(p) for p in (store.root / folder).iterdir() if p.is_file())
        except OSError:
            pass
    return max(times, default=0.0)


def _sleep(seconds: float) -> None:
    end = time.monotonic() + seconds
    while (left := end - time.monotonic()) > 0:
        time.sleep(min(SLEEP_STEP, left))


def _one_pass(args, log: Log, previous: str) -> str:
    """One pass; an error other than Ctrl+C goes to the log and the loop lives on. `foreign`/`stale`/`busy` print on a change.

    The driver of the project on another machine (`OtherHost`) is the exception: no later pass can fix it
    on this machine, so the error is logged and goes up, and the command exits with code 2.
    """
    try:
        result = once.run_pass(args, log=log)
    except once.OtherHost as err:
        log.error(str(err))
        raise
    except Exception as err:  # noqa: BLE001 - the loop does not fall: the file may be fixed by the next tick
        log.error(str(err))
        print(f"error: {err}")
        return "error"
    log.info(t("driver.pass", did=result.did, message=result.message))
    if result.did not in REPEATING_QUIET or result.did != previous:
        print(f"{result.did}: {result.message}")
    return result.did


def run_loop(args, *, log: Log | None = None, interval: float = POLL_SECONDS, passes: int = 0) -> int:
    root = context.resolve_state_dir(args.root, Path.cwd())
    store = Store(root)
    log = log or Log(store.root / "driver.log", echo=True)
    done = 0
    try:
        seen, last = state_mtime(store), time.monotonic()
        did = _one_pass(args, log, "")
        done += 1
        while not passes or done < passes:
            _sleep(interval)
            now = time.monotonic()
            mtime = state_mtime(store)
            if mtime == seen and did in QUIET and now - last < PULL_EVERY_SECONDS:
                continue
            seen, last = mtime, now
            did = _one_pass(args, log, did)
            done += 1
    except KeyboardInterrupt:
        log.info(t("driver.stopped"))
        lock.release(store)
        return 0
    return 0
