import re

import pytest
from the_nod import harness
from the_nod.adapters import default
from the_nod.driver import files
from the_nod.store import Store

def manifest(tmp_path, text):
    s = Store(tmp_path / ".nod"); (s.root / "harness.toml").write_text(text, encoding="utf-8"); return s

BASE = 'adapter = "default"\ndriver_host = ""\n[commands]\nbrief = ""\nrun = ""\naccept = ""\n'

def test_defaults_filled_by_adapter(tmp_path):
    h = harness.load(manifest(tmp_path, BASE))
    assert h.commands == default.COMMANDS and h.driver_host == ""

def test_own_command_kept_and_checked(tmp_path):
    h = harness.load(manifest(tmp_path, BASE.replace('brief = ""', 'brief = "my {card} {root}"')))
    assert h.commands["brief"] == "my {card} {root}" and h.commands["run"] == default.COMMANDS["run"]
    with pytest.raises(harness.HarnessError, match="unknown placeholder {slug} in the run command"):
        harness.load(manifest(tmp_path, BASE.replace('run = ""', 'run = "x {slug}"')))
    with pytest.raises(harness.HarnessError, match="placeholder {step_title} is for prompts only"):
        harness.load(manifest(tmp_path, BASE.replace('run = ""', 'run = "x {step_title}"')))

@pytest.mark.parametrize("text, message", [
    (BASE.replace('"default"', '"other"'), 'adapter "other" is unknown'),
    (BASE + "extra = 1\n", 'unknown key "extra"'),
    (BASE.replace('accept = ""', 'accept = 1'), "accept"),
    ("adapter = [\n", "TOML"),
])
def test_bad_manifest(tmp_path, text, message):
    with pytest.raises(harness.HarnessError, match=message):
        harness.load(manifest(tmp_path, text))

def test_messages_in_russian(tmp_path):
    from the_nod import i18n
    i18n.use("ru")
    with pytest.raises(harness.HarnessError, match="неизвестный ключ «extra»"):
        harness.load(manifest(tmp_path, BASE + "extra = 1\n"))
    with pytest.raises(harness.HarnessError, match="неизвестная подстановка {slug} в команде run"):
        harness.load(manifest(tmp_path, BASE.replace('run = ""', 'run = "x {slug}"')))

def test_missing_manifest(tmp_path):
    with pytest.raises(harness.HarnessError, match="nod init"):
        harness.load(Store(tmp_path / ".nod"))

def test_render_touches_only_known_placeholders():
    out = harness.render('x "{root}" {card} --json-schema {"a":1} {step_title}', {"root": "D:/р п", "card": "c-1", "step_title": "Шаг «1»"})
    assert out == 'x "D:/р п" c-1 --json-schema {"a":1} Шаг «1»'
    with pytest.raises(harness.HarnessError, match="{brief}"):
        harness.render("{brief}", {})

def test_init_writes_commented_default(repo, capsys):
    from the_nod.cli import main
    assert main(["--root", str(repo), "init"]) == 0
    text = (repo / ".nod" / "harness.toml").read_text(encoding="utf-8")
    assert 'adapter = "default"' in text and "{answers}" in text
    assert "# [needs]" in text
    assert harness.load(Store(repo / ".nod")).adapter == "default"


FORBIDDEN = ("git push", "git -c", "git checkout", "python -c", "python *", "bypassPermissions", "dangerously")

@pytest.mark.parametrize("commands", [default.COMMANDS])
def test_default_commands_are_narrow(commands):
    for kind, cmd in commands.items():
        assert not any(bad in cmd for bad in FORBIDDEN), (kind, cmd)
        assert ("--permission-prompts none" in cmd) <= ("--allowedTools" in cmd), kind
        assert '--disallowedTools "Edit(/.git/**),Edit(**/.git/**),' in cmd and "Edit(**/.git/**)" in cmd and "pytest*" not in cmd, kind
        assert not any(p in cmd for p in ("git status*", "git log*", "git diff*", "git status *", "git log *", "git diff *")), kind
        assert "Bash(git diff --stat)" in cmd and "Bash(git log --oneline -20)" in cmd, kind
        assert "Bash(git * --ext-diff*)" in cmd, kind
        state = ("harness.toml", "cards/**", "decisions/**", "runs/**", "acceptance/**", "order.md", "driver.lock")
        assert all(f"Edit(/.nod/{p})" in cmd for p in state), kind
        assert "Edit(/.claude/**)" in cmd and "Edit(**/.claude/**)" in cmd, kind
        assert "Edit(/.nod/driver/**)" not in cmd and "Edit(/.nod/**)" not in cmd, kind  # `driver/` stays writable
        assert f"Edit(/.nod/driver/{files.BIN_DIR}/**)" in cmd and f"Edit(**/.nod/driver/{files.BIN_DIR}/**)" in cmd, kind
        assert "--model sonnet" in cmd and "--output-format json" in cmd, kind
    assert "git commit" in commands["brief"] and "git commit" in commands["run"] and "git commit" not in commands["accept"]


def edit_denied(cmd: str, rel: str) -> bool:
    """Whether an `Edit(...)` rule of the command's `--disallowedTools` covers `rel`, a path from the repo root.

    A `/x` pattern is anchored at the root, `**/x` matches at any depth; `**` crosses folders, `*` does not.
    """
    rules = re.search(r'--disallowedTools "([^"]*)"', cmd).group(1).split(",")
    for rule in rules:
        if not (rule.startswith("Edit(") and rule.endswith(")")):
            continue
        pattern = rule[len("Edit("):-1]
        anywhere = pattern.startswith("**/")
        body = pattern[3:] if anywhere else pattern.lstrip("/")
        regex = "".join(".*" if part == "**" else "[^/]*" if part == "*" else re.escape(part)
                        for part in re.split(r"(\*\*|\*)", body))
        if re.fullmatch(("(?:.*/)?" if anywhere else "") + regex, rel):
            return True
    return False


def test_wrapper_folder_is_denied_but_results_stay_writable():
    """The `nod` wrapper heads the agent's PATH and `Bash(nod *)` is allowed: it must not be editable by the agent."""
    for kind, cmd in default.COMMANDS.items():
        for name in ("nod", "nod.cmd", "git", "python"):
            assert edit_denied(cmd, f".nod/driver/{files.BIN_DIR}/{name}"), (kind, name)
        assert edit_denied(cmd, f"sub/.nod/driver/{files.BIN_DIR}/git"), kind
        # the files of a command: the result, its activity mark, the prompt, the answers, the saved output
        for name in ("c-1.brief.toml", "c-1.run.toml", "c-1.accept.toml", "c-1.run.toml.activity",
                     "c-1.brief.prompt.md", "c-1.answers.md", "c-1.brief.out.txt", "attempts.toml"):
            assert not edit_denied(cmd, f".nod/driver/{name}"), (kind, name)
        # the helper does see the rest of the list
        assert edit_denied(cmd, ".nod/harness.toml") and edit_denied(cmd, ".nod/cards/c-1.md"), kind
        assert edit_denied(cmd, ".git/hooks/pre-commit") and not edit_denied(cmd, "src/app.py"), kind
