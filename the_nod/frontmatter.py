"""TOML frontmatter between "+++" lines: parsing and writing."""

import re
import tomllib

from the_nod.i18n import t

FENCE = "+++"
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_LINE_IN_ERROR = re.compile(r"\(at line (\d+)")
_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\t": "\\t"}


class FrontmatterError(ValueError):
    """A frontmatter parse or write error; `line` is the line number in the file."""

    def __init__(self, message: str, line: int | None = None):
        super().__init__(message)
        self.line = line


def parse(text: str) -> tuple[dict, str]:
    """Splits the text into metadata and body; without frontmatter `({}, text)`."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != FENCE:
        return {}, text
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == FENCE:
            return _load("".join(lines[1:index])), "".join(lines[index + 1:])
    raise FrontmatterError(t("frontmatter.unclosed"), len(lines))


def _load(source: str) -> dict:
    try:
        return tomllib.loads(source)
    except tomllib.TOMLDecodeError as error:
        found = _LINE_IN_ERROR.search(str(error))
        # The first TOML line is the second line of the file, after the opening "+++".
        line = int(found.group(1)) + 1 if found else None
        raise FrontmatterError(t("frontmatter.bad_toml", error=error), line) from error


def dump(meta: dict, body: str) -> str:
    """Builds the file: frontmatter from `meta`, then the body; keys with a `None` value are skipped."""
    lines = [
        f"{_key(key)} = {_value(value)}"
        for key, value in meta.items()
        if value is not None
    ]
    return "".join(f"{line}\n" for line in [FENCE, *lines, FENCE]) + body


def toml_flat(data: dict[str, str]) -> str:
    """Flat TOML without frontmatter: one `key = "value"` line per pair."""
    return "".join(f"{_key(key)} = {_string(value)}\n" for key, value in data.items())


def _key(key: str) -> str:
    return key if _BARE_KEY.fullmatch(key) else _string(key)


def _string(value: str) -> str:
    return '"' + "".join(_escape(char) for char in value) + '"'


def _escape(char: str) -> str:
    if char in _ESCAPES:
        return _ESCAPES[char]
    if ord(char) < 0x20 or ord(char) == 0x7F:
        return f"\\u{ord(char):04x}"
    return char


def _scalar(value: object) -> str:
    # bool is checked before int: bool is a subclass of int.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (int, float)):
        return repr(value)
    raise FrontmatterError(t("frontmatter.bad_type", type=type(value).__name__))


def _value(value: object) -> str:
    if isinstance(value, list):
        return _array(value)
    return _scalar(value)


def _array(items: list) -> str:
    if not items:
        return "[]"
    if all(isinstance(item, dict) for item in items):
        rows = "".join(f"  {_inline_table(item)},\n" for item in items)
        return f"[\n{rows}]"
    if all(isinstance(item, str) for item in items):
        return "[" + ", ".join(_string(item) for item in items) + "]"
    raise FrontmatterError(t("frontmatter.bad_list"))


def _inline_table(table: dict) -> str:
    pairs = ", ".join(f"{_key(key)} = {_scalar(value)}" for key, value in table.items())
    return "{ " + pairs + " }" if pairs else "{}"
