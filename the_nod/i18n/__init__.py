"""Interface language: which one is in use, and the messages of each.

The language comes from NOD_LANG (when set and not blank), then from `lang` in
`.nod/harness.toml`, then the default. It is process-wide: `cli.main` sets it from the
environment before parsing arguments, `context.open` again once the state is found.

Each language is a package (`the_nod.i18n.en`, `the_nod.i18n.ru`) whose area modules
hold `MESSAGES`; the package merges them and refuses a key defined twice.
"""

import importlib
import os
from collections.abc import Iterable, Mapping
from functools import cache
from types import MappingProxyType

LANGS = ("en", "ru")
DEFAULT = "en"
ENV = "NOD_LANG"

_current = DEFAULT


class LangError(ValueError):
    """Unknown language. The text is always English: no language is known yet when it is raised."""


def _unknown(source: str, value: object) -> LangError:
    return LangError(f"{source}={value}: unknown language, use {' or '.join(LANGS)}")


def resolve(manifest: str | None = None, env: Mapping[str, str] | None = None) -> str:
    """The language to use: NOD_LANG if set and not blank, else `manifest`, else the default."""
    env = os.environ if env is None else env
    value = env.get(ENV, "").strip()
    if value:
        if value not in LANGS:
            raise _unknown(ENV, value)
        return value
    if manifest is None:
        return DEFAULT
    if manifest not in LANGS:
        raise _unknown("lang", manifest)
    return manifest


def use(lang: str) -> None:
    """Switches the language of every following `t()` call in this process."""
    global _current
    if lang not in LANGS:
        raise _unknown("lang", lang)
    _current = lang


def current() -> str:
    return _current


@cache
def catalog(lang: str) -> Mapping[str, str]:
    """All messages of `lang`, read-only."""
    if lang not in LANGS:
        raise _unknown("lang", lang)
    return MappingProxyType(importlib.import_module(f"{__name__}.{lang}").MESSAGES)


def t(key: str, /, **values: object) -> str:
    """Message `key` in the current language with `{name}` filled from `values`.

    `key` is positional-only, so a message may have a `{key}` placeholder.
    A key missing from the catalog raises `KeyError`: the parity tests keep the catalogs complete.
    """
    return catalog(_current)[key].format(**values)


def merge(parts: Iterable[tuple[str, Mapping[str, str]]]) -> dict[str, str]:
    """One dict from `(name, messages)` pairs; a key in two parts raises `ValueError`."""
    merged: dict[str, str] = {}
    origin: dict[str, str] = {}
    for name, messages in parts:
        for key, text in messages.items():
            if key in merged:
                raise ValueError(f"message key {key!r} is defined in both {origin[key]} and {name}")
            merged[key] = text
            origin[key] = name
    return merged


def collect(package: str, areas: Iterable[str]) -> dict[str, str]:
    """`MESSAGES` of the modules `<package>.<area>` merged by `merge`."""
    names = [f"{package}.{area}" for area in areas]
    return merge((name, importlib.import_module(name).MESSAGES) for name in names)
