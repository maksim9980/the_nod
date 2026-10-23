"""Markdown importer: every `## Title` line starts a card, the lines under it are its text."""

import re

TITLE_MAX = 120

_LINE_BREAK = re.compile(r"\r\n|\r|\n")  # not str.splitlines: it also splits on \x0c, U+2028 and the like
_H1 = re.compile(r"#(?:[ \t].*)?")
_H2 = re.compile(r"##(?:[ \t](.*))?")
# A closing run of `#` counts only after a space (or alone): "Dark mode ##" is "Dark mode", "C#" stays "C#".
_CLOSING_HASHES = re.compile(r"(?:^|[ \t]+)#+[ \t]*$")
# A fence opener: 3+ backticks (no backtick later in the line, else it is inline code) or 3+ tildes.
_FENCE = re.compile(r" {0,3}(`{3,}(?=[^`]*$)|~{3,})")


def parse(text: str) -> list[tuple[str, str]]:
    """(title, body) for every `## ` heading, in file order.

    Skipped: the text before the first `## `, `# ` lines (a `# ` line also ends the card above it),
    and headings with an empty title together with their text. The body is the lines up to the next
    `## `, trimmed at the edges. A title over TITLE_MAX characters is cut and its full text goes
    to the start of the body. Lines in a closed fenced code block are plain body text; an opener
    that is never closed is an ordinary line, so it cannot hide the headings after it.
    """
    cards: list[tuple[str, str]] = []
    title: str | None = None  # None: outside a card, or in one with an empty title
    lines: list[str] = []

    def close() -> None:
        if title:
            cards.append(_card(title, lines))

    source = _LINE_BREAK.split(text)
    at = 0
    while at < len(source):
        line = source[at]
        end = _fence_end(source, at)
        if end is not None:
            lines.extend(source[at:end + 1])
            at = end + 1
            continue
        at += 1
        if _H1.fullmatch(line):
            close()
            title, lines = None, []
        elif heading := _H2.fullmatch(line):
            close()
            title, lines = _clean_title(heading.group(1) or ""), []
        else:
            lines.append(line)
    close()
    return cards


def _fence_end(lines: list[str], start: int) -> int | None:
    """The index of the line that closes the fenced block opened at `start`.

    `None` when that line is no opener or nothing closes it. A closing fence is the same character,
    at least as long as the opener, with nothing after it.
    """
    opener = _FENCE.match(lines[start])
    if opener is None:
        return None
    fence = opener.group(1)
    closing = re.compile(rf" {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*")
    return next((at for at in range(start + 1, len(lines)) if closing.fullmatch(lines[at])), None)


def _clean_title(raw: str) -> str:
    return _CLOSING_HASHES.sub("", raw.strip()).strip()


def _card(title: str, lines: list[str]) -> tuple[str, str]:
    body = "\n".join(lines).strip()
    if len(title) <= TITLE_MAX:
        return title, body
    return title[:TITLE_MAX].rstrip(), f"{title}\n\n{body}" if body else title
