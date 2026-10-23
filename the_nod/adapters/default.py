"""The default adapter: the driver commands used when a command in `harness.toml` is empty.

The strings are constants, so the flags change in one place. The `sonnet` model is the owner's choice:
the default model costs more than 1 USD per turn, and the `--max-budget-usd` limit would fire at once.
"""

# The briefs folder from the repo root: the agent puts the brief there, and the driver adopts it from there without a result.
BRIEFS_DIR = "docs/briefs"

_BASE = "claude -p --model sonnet --output-format json --permission-mode acceptEdits --permission-prompts none"

# Reading git only in fixed forms: git accepts shortened options (--outp=file), and a substring rule cannot close them.
_READ = ("Bash(git status)", "Bash(git status --short)", "Bash(git log --oneline -20)", "Bash(git log -5)",
         "Bash(git diff)", "Bash(git diff --stat)", "Bash(git diff --cached)")
_WRITE = ("Bash(git add *)", "Bash(git commit *)")
# `python3` too: stock macOS and Ubuntu have no `python` command.
_NOD = ("Bash(nod *)", "Bash(python -m the_nod *)", "Bash(python3 -m the_nod *)")
_TEST = ("Bash(python -m pytest)", "Bash(python -m pytest *)", "Bash(python3 -m pytest)", "Bash(python3 -m pytest *)")

# Denials: Edit(.git) means hooks under acceptEdits; --ext-diff runs an outside command.
# Only the driver edits the state and the manifest; `.nod/driver/` stays open: the agent writes its result there.
_DENY_STATE = tuple(f"Edit(/.nod/{p})" for p in (
    "harness.toml", "cards/**", "decisions/**", "runs/**", "acceptance/**", "order.md", "driver.lock"))
# The exception inside `.nod/driver/`: the `nod` wrapper (`driver/shim.py`, `files.BIN_DIR`) stands first in the agent's
# PATH, and `Bash(nod *)` is allowed. A wrapper the agent edited (or a `git` dropped next to it) would run any command.
_DENY_WRAPPER = ("Edit(/.nod/driver/bin/**)", "Edit(**/.nod/driver/bin/**)")
_DENY = '--disallowedTools "' + ",".join([
    "Edit(/.git/**)", "Edit(**/.git/**)", *_DENY_STATE, *_DENY_WRAPPER, "Edit(/.claude/**)", "Edit(**/.claude/**)",
    "Bash(git * --ext-diff*)"]) + '"'


def _allowed(*groups: tuple[str, ...]) -> str:
    return '--allowedTools "' + ",".join([*(tool for group in groups for tool in group), "Agent"]) + '"'


ALLOWED_BRIEF = _allowed(_READ, _WRITE, _NOD)
ALLOWED_RUN = _allowed(_READ, _WRITE, _NOD, _TEST)
ALLOWED_ACCEPT = _allowed(_READ, _NOD, _TEST)

BRIEF_BUDGET_USD = 5
RUN_BUDGET_USD = 30
ACCEPT_BUDGET_USD = 10

COMMANDS: dict[str, str] = {
    "brief": f"{_BASE} {ALLOWED_BRIEF} {_DENY} --max-budget-usd {BRIEF_BUDGET_USD}",
    "run": f"{_BASE} {ALLOWED_RUN} {_DENY} --max-budget-usd {RUN_BUDGET_USD}",
    "accept": f"{_BASE} {ALLOWED_ACCEPT} {_DENY} --max-budget-usd {ACCEPT_BUDGET_USD}",
}
