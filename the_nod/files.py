"""File helpers: a file name from a title and an atomic text write."""

import os
import re
import tempfile
from pathlib import Path

_NOT_SLUG = re.compile(r"[^\w-]|_")
_DASHES = re.compile(r"-{2,}")


def slugify(title: str, max_len: int = 40) -> str:
    """A file name from a title: lower case, letters of any script, digits and "-"."""
    slug = _DASHES.sub("-", _NOT_SLUG.sub("-", title.lower()))
    return slug[:max_len].strip("-")


def write_text_atomic(path: Path, text: str) -> None:
    """Writes the file through a temporary file next to it and `os.replace`; UTF-8, `\\n` line ends."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as tmp:
            tmp.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
