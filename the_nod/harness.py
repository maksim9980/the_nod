"""The `.nod/harness.toml` manifest: reading, checking, placeholders in commands."""
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from the_nod import i18n
from the_nod.adapters import default
from the_nod.errors import HarnessError
from the_nod.i18n import t
from the_nod.portability.needs import Needs, validate_needs
from the_nod.store import Store

MANIFEST = "harness.toml"
ADAPTERS = ("default",)
COMMAND_KINDS = ("brief", "run", "accept")
PLACEHOLDERS = ("card", "title", "brief", "root", "answers", "result", "prompt", "step", "step_title", "run")
# A command goes to the shell: the free text of titles never gets into it.
PROMPT_ONLY = ("title", "step_title")
COMMAND_PLACEHOLDERS = tuple(name for name in PLACEHOLDERS if name not in PROMPT_ONLY)
__all__ = ("Harness", "HarnessError", "load", "read_lang", "read_push", "render", "validate")
TOP_KEYS = ("lang", "adapter", "driver_host", "commands", "git", "needs")
# `[git]`: `push = true` syncs the state with origin; without it Nod never talks to a remote.
GIT_KEYS = ("push",)

_ADAPTER_COMMANDS = {"default": default.COMMANDS}
_ADAPTER_BRIEFS = {"default": default.BRIEFS_DIR}
_NAME = re.compile(r"\{([a-z_]+)\}")
_KNOWN = re.compile(r"\{(%s)\}" % "|".join(PLACEHOLDERS))


@dataclass(frozen=True)
class Harness:
    adapter: str
    driver_host: str
    commands: dict[str, str]
    # The briefs folder from the repo root comes from the adapter; the manifest has no key for it.
    briefs_dir: str = default.BRIEFS_DIR
    # What the project needs from the machine: `nod doctor` checks it.
    needs: Needs = Needs()
    # Interface language of the project; NOD_LANG wins over it.
    lang: str = i18n.DEFAULT
    # `[git] push`: pull before every write and push after it; off by default, the state stays local.
    push: bool = False


def _check_command(kind: str, command: str) -> None:
    for name in _NAME.findall(command):
        if name in PROMPT_ONLY:
            raise HarnessError(t("harness.prompt_only", name=name))
        if name not in COMMAND_PLACEHOLDERS:
            raise HarnessError(t("harness.unknown_placeholder", name=name, kind=kind))


def _string(key: str, value) -> str:
    if not isinstance(value, str):
        raise HarnessError(t("harness.not_string", key=key))
    return value


def _lang(value) -> str:
    lang = _string("lang", value)
    if lang not in i18n.LANGS:
        raise HarnessError(t("harness.bad_lang", value=lang))
    return lang


def _push(value) -> bool:
    """`push` of the `[git]` table; a missing table or key means local only."""
    if not isinstance(value, dict):
        raise HarnessError(t("harness.not_table", key="git"))
    for key in value:
        if key not in GIT_KEYS:
            raise HarnessError(t("harness.unknown_key", key=f"git.{key}"))
    push = value.get("push", False)
    if not isinstance(push, bool):
        raise HarnessError(t("harness.not_bool", key="git.push"))
    return push


def validate(data: dict) -> Harness:
    for key in data:
        if key not in TOP_KEYS:
            raise HarnessError(t("harness.unknown_key", key=key))
    lang = _lang(data.get("lang", i18n.DEFAULT))
    adapter = _string("adapter", data.get("adapter", "default"))
    if adapter not in ADAPTERS:
        raise HarnessError(t("harness.unknown_adapter", adapter=adapter, allowed=", ".join(ADAPTERS)))
    driver_host = _string("driver_host", data.get("driver_host", ""))
    raw = data.get("commands", {})
    if not isinstance(raw, dict):
        raise HarnessError(t("harness.not_table", key="commands"))
    for key in raw:
        if key not in COMMAND_KINDS:
            raise HarnessError(t("harness.unknown_key", key=key))
    commands: dict[str, str] = {}
    for kind in COMMAND_KINDS:
        command = _string(f"commands.{kind}", raw.get(kind, ""))
        if command.strip():
            _check_command(kind, command)
        commands[kind] = command if command.strip() else _ADAPTER_COMMANDS[adapter][kind]
    needs = validate_needs(data.get("needs", {}))
    push = _push(data.get("git", {}))
    return Harness(adapter, driver_host, commands, _ADAPTER_BRIEFS[adapter], needs, lang, push)


def load(store: Store) -> Harness:
    path = store.root / MANIFEST
    if not path.exists():
        raise HarnessError(t("harness.missing"))
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as error:
        raise HarnessError(t("harness.bad_toml", path=path, error=error)) from error
    except (OSError, UnicodeDecodeError) as error:
        raise HarnessError(t("harness.unreadable", path=path, error=error)) from error
    return validate(data)


def _read(state_dir: Path) -> dict | None:
    """The parsed manifest in `state_dir`, or `None` when it is missing or does not parse."""
    try:
        return tomllib.loads((Path(state_dir) / MANIFEST).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None


def read_lang(state_dir: Path) -> str | None:
    """`lang` of the manifest in `state_dir`, or `None` without the file or the key.

    A manifest that does not parse also gives `None`: `load` reports that error in its own words.
    An invalid value raises `HarnessError`.
    """
    data = _read(state_dir)
    return _lang(data["lang"]) if data is not None and "lang" in data else None


def read_push(state_dir: Path) -> bool:
    """`[git] push` of the manifest in `state_dir`; `False` without the file, the table or the key.

    A manifest that exists but does not read or parse also gives `False` (never talk to a remote
    by mistake), with one warning line on stderr: a `push = true` project would otherwise go local
    silently. An invalid `[git]` table raises `HarnessError`.
    """
    path = Path(state_dir) / MANIFEST
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return False
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        print(t("harness.push_unread", path=path, error=" ".join(str(error).split())), file=sys.stderr)
        return False
    return _push(data.get("git", {}))


def render(template: str, values: dict[str, str]) -> str:
    def substitute(match: re.Match) -> str:
        name = match.group(1)
        if name not in values:
            raise HarnessError(t("harness.no_value", name=name))
        return values[name]
    return _KNOWN.sub(substitute, template)
