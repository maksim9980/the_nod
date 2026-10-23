"""Plural forms of the words in the review: which of the three catalog messages a number takes.

Each language has its own rule. A word comes in three messages (`_one`, `_few`, `_many`); a language with
fewer forms repeats one of them.
"""

from collections.abc import Callable

from the_nod import i18n

ONE, FEW, MANY = "one", "few", "many"


def _english(n: int) -> str:
    return ONE if n == 1 else MANY


def _russian(n: int) -> str:
    """Russian: 1, 21, 31 take the first form; 2-4, 22-24 the second; the rest, and 11-14, the third."""
    if n % 10 == 1 and n % 100 != 11:
        return ONE
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return FEW
    return MANY


RULES: dict[str, Callable[[int], str]] = {"en": _english, "ru": _russian}


def form(n: int) -> str:
    """The form `n` takes in the current language: `one`, `few` or `many`."""
    return RULES[i18n.current()](n)


def pick(n: int, one: str, few: str, many: str) -> str:
    """The text of the message among the three keys that `n` takes in the current language."""
    return i18n.t({ONE: one, FEW: few, MANY: many}[form(n)])
