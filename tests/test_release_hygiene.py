"""Release hygiene: one name, one version, English by default, no leftovers.

Every check reads `git ls-files`: what is tracked is what ships. Untracked scratch files do not count.
"""

import ast
import fnmatch
import io
import json
import re
import subprocess
import tokenize
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest

from the_nod import __version__
from the_nod.mcp import server

ROOT = Path(__file__).resolve().parent.parent
VERSION = "0.1.0"

# An exemption is a rule: the lines of a file (0-based indexes) that may keep what the check looks for.
Rule = Callable[[list[str]], set[int]]


def _whole_file(lines: list[str]) -> set[int]:
    return set(range(len(lines)))


def _lines_with(word: str) -> Rule:
    return lambda lines: {index for index, line in enumerate(lines) if word in line}


def _section(start: str, stop: str | None) -> Rule:
    """The lines from the first one that matches `start` up to the next one that matches `stop`, or to the end.

    A file without the `start` line keeps nothing.
    """
    begins, stops = re.compile(start), re.compile(stop) if stop else None

    def rule(lines: list[str]) -> set[int]:
        first = next((index for index, line in enumerate(lines) if begins.match(line)), None)
        if first is None:
            return set()
        end = next((index for index in range(first + 1, len(lines)) if stops and stops.match(lines[index])), len(lines))
        return set(range(first, end))

    return rule


CYRILLIC = re.compile("[Ѐ-ӿ]")
INTERNAL = ("docs/plans/",)  # the working plan; removed before the release

# Files and folders that carry Russian on purpose.
RUSSIAN_PREFIXES = (
    "the_nod/i18n/ru/",  # the Russian dictionary
    "the_nod/prompts/default/ru/",  # the Russian agent prompts
)
RUSSIAN_FILES = {
    "the_nod/adapters/briefs.py",  # Russian brief markers, accepted next to the English ones
    "the_nod/migrate.py",  # values and markers of the old state, which was Russian
    "mod/nod-pane/hooks/texts/ru.ts",  # the Russian pane dictionary
}
RUSSIAN_GLOBS = ("docs/launch/*-ru.md",)  # launch posts in Russian
RUSSIAN_SECTIONS: dict[str, Rule] = {
    # The CLAUDE.md snippet: English first, then its Russian twin, from the heading with "Russian" to the end.
    "docs/agents.md": _section(r"##\s.*\bRussian\b", None),
}
# Test code is not scanned as a whole: Russian data is the point of the Russian checks.
# `test_test_sources_are_english` covers its comments, docstrings and names instead.
UNSCANNED_FOR_RUSSIAN = ("tests/", "mod/nod-pane/tests/")

# The old product name: forbidden everywhere except the migration.
OLD_NAME = re.compile(r"(?i:sprintboot)|SB_[A-Z]|(?<![\w-])sb(?![\w-])")
OLD_NAME_ALLOWED: dict[str, Rule] = {
    "the_nod/migrate.py": _whole_file,
    "the_nod/commands/migrate.py": _whole_file,
    "the_nod/i18n/en/migrate.py": _whole_file,
    "the_nod/i18n/ru/migrate.py": _whole_file,
    "tests/test_migrate.py": _whole_file,
    "mod/nod-pane/hooks/find.ts": _whole_file,  # looks for the old folder
    "mod/nod-pane/hooks/texts/en.ts": _lines_with("legacyFound"),  # the migration hint, and only it
    "mod/nod-pane/hooks/texts/ru.ts": _lines_with("legacyFound"),
    # The paragraph "Migrating from `.sprintboot/`": from its heading to the next `## ` heading.
    "docs/cli.md": _section(r"## Migrating from", r"## "),
    "CHANGELOG.md": _whole_file,
    "tests/test_release_hygiene.py": _whole_file,  # this file names the patterns
}

# The repository placeholder, until the owner picks the real one (the replace command is in docs/publish.md).
_OWNER = "OWN" + "ER"  # split: the replace command of the release must not rewrite this very pattern
OWNER_PLACEHOLDER = re.compile(rf"{_OWNER}/the_nod|github\.com/{_OWNER}\b")
OWNER_PLACEHOLDER_ALLOWED = (
    "pyproject.toml",
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "CHANGELOG.md",
    ".github/ISSUE_TEMPLATE/config.yml",
    "docs/*",
)


def _tracked() -> list[str]:
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout: nothing to list")
    done = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    names = done.stdout.decode("utf-8").split("\0")
    return [name for name in names if name and (ROOT / name).is_file()]


def _text(name: str) -> str | None:
    """The text of a tracked file; `None` for a binary one (a NUL byte)."""
    data = (ROOT / name).read_bytes()
    if b"\0" in data:
        return None
    return data.decode("utf-8", errors="replace")


def _findings(name: str, text: str, pattern: re.Pattern, rules: dict[str, Rule]) -> list[str]:
    """`path:line: text` for each line of `text` that matches `pattern` and is not freed by the rule of `name`."""
    lines = text.splitlines()
    free = rules[name](lines) if name in rules else set()
    return [f"{name}:{number}: {line.strip()[:120]}" for number, line in enumerate(lines, 1)
            if pattern.search(line) and number - 1 not in free]


def _hits(names: list[str], pattern: re.Pattern, rules: dict[str, Rule] | None = None) -> list[str]:
    """`_findings` over the tracked files `names`; a binary file has none."""
    found = []
    for name in names:
        text = _text(name)
        if text is not None:
            found += _findings(name, text, pattern, rules or {})
    return found


def _internal(name: str) -> bool:
    return name.startswith(INTERNAL)


def test_versions_agree():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    asked = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    handshake = server.handle(asked, None)["result"]["serverInfo"]
    assert pyproject["project"]["dynamic"] == ["version"] and "version" not in pyproject["project"]
    assert pyproject["tool"]["setuptools"]["dynamic"]["version"] == {"attr": "the_nod.__version__"}
    assert __version__ == plugin["version"] == handshake["version"] == VERSION
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(rf"^## \[{re.escape(VERSION)}\]", changelog, re.MULTILINE)


def test_names():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert pyproject["project"]["name"] == "the-nod"
    assert pyproject["project"]["scripts"] == {"nod": "the_nod.cli:main"}
    assert plugin["name"] == market["name"] == market["plugins"][0]["name"] == "nod"
    assert list(plugin["mcpServers"]) == ["nod"] and "core" in plugin["userConfig"]
    assert (ROOT / "the_nod" / "__init__.py").is_file() and (ROOT / "mod" / "nod-pane" / "hooks").is_dir()


def test_no_cyrillic_outside_ru():
    """With `lang = "en"` nothing Russian may reach the person; the files that hold none are checked whole."""
    def russian(name: str) -> bool:
        return (name.startswith(RUSSIAN_PREFIXES) or name in RUSSIAN_FILES
                or any(fnmatch.fnmatchcase(name, glob) for glob in RUSSIAN_GLOBS))

    names = [name for name in _tracked()
             if not russian(name) and not _internal(name) and not name.startswith(UNSCANNED_FOR_RUSSIAN)]
    assert names, "the file list is empty: the check checks nothing"
    found = _hits(names, CYRILLIC, RUSSIAN_SECTIONS)
    assert not found, "Cyrillic outside the Russian files:\n" + "\n".join(found)


def test_old_name_only_in_migration():
    names = [name for name in _tracked() if not _internal(name)]
    found = _hits(names, OLD_NAME, OLD_NAME_ALLOWED)
    found += [f"{name}: the path carries the old name" for name in names
              if OLD_NAME.search(name) and name not in OLD_NAME_ALLOWED]
    assert not found, "The old name outside the migration:\n" + "\n".join(found)


def test_no_owner_placeholder_left_except_known():
    names = _tracked()
    free = {name: _whole_file for name in names
            if any(fnmatch.fnmatchcase(name, glob) for glob in OWNER_PLACEHOLDER_ALLOWED)}
    found = _hits(names, OWNER_PLACEHOLDER, free)
    assert not found, "The repository placeholder outside the known files:\n" + "\n".join(found)


# --- the exemptions are as narrow as they say (in-memory probes) -------------------------------------------------

CLI_DOC = """# Commands

## Commands

Run `sb card add`.

## Migrating from `.sprintboot/`

The older version was called SprintBoot.
It used `sb` too.

## Exit codes

See `sb status`.
"""


def _numbers(found: list[str]) -> list[int]:
    return [int(entry.split(":")[1]) for entry in found]


def test_old_name_exemption_of_cli_md_is_the_migration_section_only():
    found = _findings("docs/cli.md", CLI_DOC, OLD_NAME, OLD_NAME_ALLOWED)
    assert _numbers(found) == [5, 14]  # `sb card add` under Commands, `sb status` after the section
    renamed = CLI_DOC.replace("Migrating from", "Moving on from")
    assert _numbers(_findings("docs/cli.md", renamed, OLD_NAME, OLD_NAME_ALLOWED)) == [5, 7, 9, 10, 14]  # no section: nothing is free
    last = CLI_DOC.replace("## Exit codes\n\nSee `sb status`.\n", "")
    assert _numbers(_findings("docs/cli.md", last, OLD_NAME, OLD_NAME_ALLOWED)) == [5]  # the section may be the last one
    assert _numbers(_findings("docs/other.md", CLI_DOC, OLD_NAME, OLD_NAME_ALLOWED)) == [5, 7, 9, 10, 14]


def test_old_name_exemption_of_the_pane_texts_is_the_hint_line_only():
    texts = "export const en = {\n  legacyFound: 'found .sprintboot/ from an older version',\n  other: 'run sb',\n}\n"
    assert _numbers(_findings("mod/nod-pane/hooks/texts/en.ts", texts, OLD_NAME, OLD_NAME_ALLOWED)) == [3]


AGENTS_DOC = """# Owner actions for your agents

## The rule in English

Ask the owner through a decision.

## The rule in Russian

## Действия владельца

Не спрашивай в чате.
"""


def test_russian_exemption_of_agents_md_starts_at_the_russian_heading():
    assert _findings("docs/agents.md", AGENTS_DOC, CYRILLIC, RUSSIAN_SECTIONS) == []
    english_part = AGENTS_DOC.replace("Ask the owner", "Спроси владельца")
    assert _numbers(_findings("docs/agents.md", english_part, CYRILLIC, RUSSIAN_SECTIONS)) == [5]
    no_heading = AGENTS_DOC.replace("## The rule in Russian", "## The same rule")
    assert _numbers(_findings("docs/agents.md", no_heading, CYRILLIC, RUSSIAN_SECTIONS)) == [9, 11]
    assert _numbers(_findings("docs/guide.md", AGENTS_DOC, CYRILLIC, RUSSIAN_SECTIONS)) == [9, 11]


# --- test sources: English comments, docstrings and names -------------------------------------------------------

_STRING = re.compile(r"""(['"`])(?:\\.|(?!\1).)*\1""")
_TS_TITLE = re.compile(r"""^\s*(?:test|it|describe)(?:\.\w+)*\(\s*(['"`])(.*?)\1""")


def _python_findings(name: str, source: str) -> list[str]:
    found = []
    docstrings = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstrings.update(range(first.lineno, first.end_lineno + 1))
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if not CYRILLIC.search(token.string):
            continue
        if token.type == tokenize.COMMENT:
            found.append(f"{name}:{token.start[0]}: comment")
        elif token.type == tokenize.NAME:
            found.append(f"{name}:{token.start[0]}: name {token.string!r}")
        elif token.type == tokenize.STRING and token.start[0] in docstrings:
            found.append(f"{name}:{token.start[0]}: docstring")
    return found


def _typescript_findings(name: str, source: str) -> list[str]:
    found = []
    for number, line in enumerate(source.splitlines(), 1):
        title = _TS_TITLE.match(line)
        if title and CYRILLIC.search(title.group(2)):
            found.append(f"{name}:{number}: test title")
        code = _STRING.sub('""', line)
        comment = re.search(r"//|/\*|^\s*\*", code)
        if comment and CYRILLIC.search(code[comment.start():]):
            found.append(f"{name}:{number}: comment")
    return found


def test_test_sources_are_english():
    """Russian stays in the data of the Russian checks; comments, docstrings, names and titles are English."""
    found = []
    checked = 0
    for name in _tracked():
        in_tests = name.startswith(UNSCANNED_FOR_RUSSIAN)
        if not in_tests or name.startswith("tests/fixtures/"):
            continue
        source = _text(name)
        if source is None:
            continue
        checked += 1
        if name.endswith(".py"):
            found += _python_findings(name, source)
        elif name.endswith((".ts", ".tsx")):
            found += _typescript_findings(name, source)
        elif name.endswith(".ps1"):
            found += _hits([name], CYRILLIC)
    assert checked > 20, "too few test files seen: the check checks nothing"
    assert not found, "Russian in test comments, docstrings or names:\n" + "\n".join(found)
