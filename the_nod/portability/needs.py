"""The `[needs]` section of the manifest: what a project needs from the machine."""
import re
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import NoReturn

from the_nod.errors import HarnessError
from the_nod.i18n import t

JOBS = ("driver",)
NEEDS_KEYS = ("python", "nod", "claude", "jobs", "skills", "agents", "rules")
COPY_KINDS = ("skills", "agents", "rules")

_STRINGS = ("python", "nod", "claude")
_VERSION = re.compile(r"\d+\.\d+")


@dataclass(frozen=True)
class Needs:
    python: str = "3.13"
    nod: str = ""
    claude: str = "claude"
    jobs: tuple[str, ...] = ("driver",)
    skills: tuple[str, ...] = ()
    agents: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()


def _fail(message: str) -> NoReturn:
    raise HarnessError(message)


def _string(key: str, value) -> str:
    if not isinstance(value, str):
        _fail(t("needs.not_string", key=key))
    return value


def _strings(key: str, value) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        _fail(t("needs.not_strings", key=key))
    return tuple(value)


def _inside_repo(path: str) -> bool:
    """The path is relative on every platform and does not leave the repo through `..`."""
    windows, posix = PureWindowsPath(path), PurePosixPath(path)
    if not path.strip() or windows.drive or windows.root or posix.is_absolute():
        return False
    if posix.name in ("", ".") or windows.name in ("", "."):  # "." and "./" are the whole repo
        return False
    return ".." not in windows.parts


def _paths(key: str, value) -> tuple[str, ...]:
    paths = _strings(key, value)
    for path in paths:
        if not _inside_repo(path):
            _fail(t("needs.bad_path", key=key, path=path))
    return paths


def _jobs(value) -> tuple[str, ...]:
    jobs = _strings("jobs", value)
    for job in jobs:
        if job not in JOBS:
            _fail(t("needs.unknown_job", job=job, known=", ".join(JOBS)))
    return jobs


def validate_needs(data: dict) -> Needs:
    """Checks the `[needs]` section; the keys left out take the defaults of `Needs`."""
    if not isinstance(data, dict):
        _fail(t("needs.not_table"))
    for key in data:
        if key not in NEEDS_KEYS:
            _fail(t("needs.unknown_key", key=key))
    values = {key: _string(key, data[key]) for key in _STRINGS if key in data}
    if "python" in values and not _VERSION.fullmatch(values["python"]):
        _fail(t("needs.bad_python", value=values["python"]))
    if "jobs" in data:
        values["jobs"] = _jobs(data["jobs"])
    for kind in COPY_KINDS:
        if kind in data:
            values[kind] = _paths(kind, data[kind])
    return Needs(**values)


def python_floor(needs: Needs) -> tuple[int, int]:
    """The lowest Python version of `needs.python`."""
    major, minor = needs.python.split(".")
    return int(major), int(minor)
