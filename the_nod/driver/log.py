"""The driver log: `<time> <LEVEL> <text>` lines, appended, rotated by size."""

import os
import sys
from pathlib import Path

from the_nod.model import now_iso

ROTATE_BYTES = 1_000_000


class Log:
    def __init__(self, path: Path, echo: bool = False):
        self.path = path
        self.echo = echo

    def info(self, msg: str) -> None:
        self._write("INFO", msg)

    def warn(self, msg: str) -> None:
        self._write("WARN", msg)

    def error(self, msg: str) -> None:
        self._write("ERROR", msg)

    def _write(self, level: str, msg: str) -> None:
        line = f"{now_iso()} {level} {msg}\n"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > ROTATE_BYTES:
                os.replace(self.path, self.path.with_name(self.path.name + ".1"))
            with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(line)
        except OSError:
            print(line, end="", file=sys.stderr)
            return
        if self.echo:
            print(line, end="")
