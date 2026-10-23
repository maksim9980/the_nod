"""The local driver folder `.nod/driver/`: file paths, attempts, placeholders.

The folder is in `.gitignore`: everything here lives only on the driver machine.
"""

import argparse
import re
import tomllib
from pathlib import Path

from the_nod import context, harness, i18n, prompts
from the_nod.context import Context
from the_nod.i18n import t
from the_nod.model import Card
from the_nod.store import Store, write_text_atomic

MAX_ATTEMPTS = 2
ATTEMPTS_FILE = "attempts.toml"
BIN_DIR = "bin"  # the `nod` wrappers for the agent commands, `.nod/driver/bin/` (`shim.py`)
OUTPUT_LIMIT = 64 * 1024  # bytes of the agent stdout and stderr tail kept on disk
# Placeholder values go into a shell line: quotes, command separators and control characters
# are refused in them. A repo root with non-ASCII letters and spaces is fine.
# `<`, `>`, `^` are cmd redirection and escaping; `%`, `!` and parentheses are fine: "Program Files (x86)".
SHELL_UNSAFE = frozenset("\"';&|`$<>^")  # and any control character, a newline included
BRIEF_PATH = re.compile(r"[A-Za-z0-9._/-]+")


def driver_dir(store: Store) -> Path:
    path = store.root / "driver"
    path.mkdir(parents=True, exist_ok=True)
    return path


def result_path(store: Store, card_id: str, kind: str) -> Path:
    return driver_dir(store) / f"{card_id}.{kind}.toml"


def prompt_path(store: Store, card_id: str, kind: str) -> Path:
    return driver_dir(store) / f"{card_id}.{kind}.prompt.md"


def answers_path(store: Store, card_id: str) -> Path:
    return driver_dir(store) / f"{card_id}.answers.md"


def output_paths(store: Store, card_id: str, kind: str) -> tuple[Path, Path]:
    """The stdout and stderr files of the last `kind` command of the card."""
    base = driver_dir(store)
    return base / f"{card_id}.{kind}.out.txt", base / f"{card_id}.{kind}.err.txt"


def _tail(text: str) -> bytes:
    """The last `OUTPUT_LIMIT` bytes of utf-8 without a cut character."""
    data = text.encode("utf-8", errors="replace")
    if len(data) <= OUTPUT_LIMIT:
        return data
    return data[-OUTPUT_LIMIT:].decode("utf-8", errors="ignore").encode("utf-8")


def save_output(store: Store, card_id: str, kind: str, outcome) -> tuple[Path, Path]:
    """The stdout and stderr tails of the command to disk, overwriting; the file paths."""
    out, err = output_paths(store, card_id, kind)
    out.write_bytes(_tail(outcome.stdout))
    err.write_bytes(_tail(outcome.stderr))
    return out, err


# --- attempts ---

def attempts(store: Store) -> dict[str, int]:
    """Failed attempts by card; an unreadable file counts as empty."""
    path = driver_dir(store) / ATTEMPTS_FILE
    if not path.exists():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}
    return {k: v for k, v in data.items() if type(v) is int}


def _save_attempts(store: Store, data: dict[str, int]) -> None:
    text = "".join(f'"{k}" = {v}\n' for k, v in sorted(data.items()))
    write_text_atomic(driver_dir(store) / ATTEMPTS_FILE, text)


def bump_attempt(store: Store, card_id: str) -> int:
    data = attempts(store)
    n = data.get(card_id, 0) + 1
    _save_attempts(store, {**data, card_id: n})
    return n


def clear_attempt(store: Store, card_id: str) -> None:
    data = attempts(store)
    if card_id in data:
        _save_attempts(store, {k: v for k, v in data.items() if k != card_id})


# --- placeholders and the command environment ---

def repo_root(store: Store) -> Path:
    return store.root.absolute().parent


def brief_path(root: Path, value: str) -> str:
    """The brief path from the repo root as `docs/x.md`; `ValueError` if it is unsafe or the file is missing.

    Only `[A-Za-z0-9._/-]` is allowed, without `..` and without a leading `/`; the file lies inside `root`.
    Backslashes (a Windows path) become forward slashes first.
    """
    error = ValueError(t("driver.bad_brief_path", path=value))
    value = value.replace("\\", "/")
    parts = value.split("/")
    if not BRIEF_PATH.fullmatch(value) or value.startswith("/") or ".." in parts:
        raise error
    base = root.resolve()
    path = (base / value).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise error
    return path.relative_to(base).as_posix()


def placeholders(ctx: Context, card: Card, *, kind: str, step: int | None = None,
                 run: str | None = None) -> dict[str, str]:
    """Values of all `harness.PLACEHOLDERS`; the paths are absolute except `brief` (from the repo root).

    An unsafe `card.brief` is a `HarnessError`: no command starts with it.
    """
    store = ctx.store
    brief = ""
    if card.brief:
        try:
            brief = brief_path(repo_root(store), card.brief)
        except ValueError as err:
            raise harness.HarnessError(str(err)) from err
    step_title = next((s.title for s in card.steps if s.n == step), "") if step is not None else ""
    return {
        "card": card.id,
        "title": card.title,
        "brief": brief,
        "root": str(repo_root(store)),
        "answers": str(answers_path(store, card.id).absolute()),
        "result": str(result_path(store, card.id, kind).absolute()),
        "prompt": str(prompt_path(store, card.id, kind).absolute()),
        "step": "" if step is None else str(step),
        "step_title": step_title,
        "run": run or "",
    }


def _unsafe(value: str) -> bool:
    return any(ch in SHELL_UNSAFE or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value)


def command_values(values: dict[str, str]) -> dict[str, str]:
    """Only what may go into a shell line: no titles and no unsafe characters."""
    picked = {k: values[k] for k in harness.COMMAND_PLACEHOLDERS}
    for name, value in picked.items():
        if _unsafe(value):
            raise harness.HarnessError(t("driver.unsafe_placeholder", name=name))
    return picked


def env_from(values: dict[str, str]) -> dict[str, str]:
    """The agent command environment: the placeholders as `NOD_<NAME>` and the `NOD_AGENT=1` mark."""
    return {**{f"NOD_{name.upper()}": value for name, value in values.items()}, context.AGENT_ENV: "1"}


def prompt_text(adapter: str, kind: str, values: dict[str, str], card: Card) -> str:
    """The rendered prompt in the current language, then the card block: the prompts say the card body is below.

    A brief with a non-empty `{brief}` gets the rebrief lines (`brief-again.md`) before the card.
    """
    lang = i18n.current()
    text = harness.render(prompts.load(adapter, kind, lang), values).rstrip("\n")
    if kind == "brief" and values.get("brief"):
        again = harness.render(prompts.load(adapter, "brief-again", lang), values).strip("\n")
        text = f"{text}\n\n{again}"
    return f"{text}\n\n\n{t('driver.prompt_card')}\n{card.title}\n\n{card.body}"


def reopen(ctx: Context) -> Context:
    """A fresh context after a long agent command: a new pull and a new time, the same `[git] push` mode."""
    return context.open(argparse.Namespace(root=str(ctx.store.root)), remote=ctx.remote)
