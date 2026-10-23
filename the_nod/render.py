"""Views of `.nod`: the texts of BACKLOG.md and BACKLOG-ARCHIVE.md, in the current language."""

from the_nod.i18n import t
from the_nod.model import Card, Step
from the_nod.store import Store

_UNKNOWN_DATE = "?"
_DATE_LEN = 10


def _head(title: str, name: str) -> list[str]:
    return [t("render.head", title=title), "", t("render.warning", name=name)]


def _step(step: Step) -> str:
    return f"{step.n}. ~~{step.title}~~" if step.done else f"{step.n}. {step.title}"


def _body(card: Card) -> list[str]:
    text = card.body.rstrip()
    return [text] if text else []


def _active(card: Card) -> list[str]:
    lines = ["", f"## {card.title}", ""]
    if card.brief:
        lines += [t("render.brief", brief=card.brief), ""]
    return lines + _body(card) + [_step(s) for s in card.steps] + ["", "---"]


def _done(card: Card) -> list[str]:
    date = card.closed_at[:_DATE_LEN] if card.closed_at else _UNKNOWN_DATE
    return ["", t("render.done", title=card.title, date=date), ""] + _body(card) + ["", "---"]


def _text(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def backlog(store: Store) -> str:
    """BACKLOG.md: active cards in the `order()` order."""
    lines = _head("BACKLOG", "backlog") + ["", t("render.active")]
    for id in store.order():
        lines += _active(store.load_card(id))
    return _text(lines)


def archive(store: Store) -> str:
    """BACKLOG-ARCHIVE.md: closed cards, newest first."""
    done = sorted((c for c in store.cards() if c.status == "done"), key=lambda c: c.id)
    done.sort(key=lambda c: c.closed_at or "", reverse=True)
    lines = _head("BACKLOG-ARCHIVE", "archive")
    for card in done:
        lines += _done(card)
    return _text(lines)
