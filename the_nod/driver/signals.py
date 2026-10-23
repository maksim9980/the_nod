"""Stopping the driver by a signal on POSIX: SIGTERM and SIGHUP become `SystemExit`.

`agent.run_command` starts the agent in its own session, so a signal sent to the driver
(launchd `bootout`, systemd `stop`, a closed terminal) does not reach the agent. The
`SystemExit` unwinds the driver through the `finally` of the agent wait, which kills the
agent's process group, and through the `finally` that releases the driver lock.
"""

import contextlib
import signal
import sys
import threading
from collections.abc import Iterator

EXIT_BASE = 128  # the shell convention: killed by signal N exits with 128 + N
STOP_SIGNALS = ("SIGTERM", "SIGHUP")
STOP_EXIT_CODES = (EXIT_BASE + 1, EXIT_BASE + 15)  # SIGHUP, SIGTERM: the same numbers on Linux and macOS


def _exit(signum: int, frame: object) -> None:
    raise SystemExit(EXIT_BASE + signum)


@contextlib.contextmanager
def exit_on_signals() -> Iterator[None]:
    """For the time of the block, SIGTERM and SIGHUP raise `SystemExit`; the old handlers come back after.

    An ignored SIGHUP (`nohup`) stays ignored. Nothing changes on Windows or outside the main thread
    (`signal.signal` works only there).
    """
    if sys.platform == "win32" or threading.current_thread() is not threading.main_thread():
        yield
        return
    numbers = [getattr(signal, name) for name in STOP_SIGNALS]
    # `nohup nod driver &` ignores SIGHUP on purpose: a closed terminal must not stop that driver.
    numbers = [number for number in numbers
               if not (number == signal.SIGHUP and signal.getsignal(number) is signal.SIG_IGN)]
    previous = {number: signal.signal(number, _exit) for number in numbers}
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
