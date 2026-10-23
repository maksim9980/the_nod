"""The brief format (decision R5) and the agent prompts of both languages."""
import re
import shlex
from pathlib import Path

import pytest

from the_nod import harness, i18n, model, prompts
from the_nod.adapters import briefs, default
from the_nod.cli import build_parser

CYRILLIC = re.compile(r"[Ѐ-ӿ]")
FIXTURES = Path(__file__).parent / "fixtures"
KINDS = ("brief", "brief-again", "run", "accept")
FORK_LABEL = {"en": "Question:", "ru": "Вопрос:"}
FORK_EN = "2. Question: Keep history? Proposed: yes, 30 days. Why: enough to debug. Options: yes, 30 days | no | forever."
FORK_RU = ("2. Вопрос: Хранить ли историю? Предлагаю: да, 30 дней. Почему: хватит для разбора. "
           "Варианты: да, 30 дней | нет | навсегда.")
VALUES = {"root": "/repo", "card": "c-1", "result": "r.toml", "answers": "a.toml", "brief": "b.md",
          "title": "T", "step": "1", "step_title": "S", "run": "run-1"}


def read(rel: str) -> str:
    return (FIXTURES / rel).read_text(encoding="utf-8")


def rendered(kind: str, lang: str) -> str:
    return harness.render(prompts.load("default", kind, lang), VALUES)


# --- the fixtures: one Tidepool brief in each language ---

@pytest.mark.parametrize("lang", i18n.LANGS)
def test_fixture_brief_parses(lang):
    b = briefs.parse_brief(read(f"briefs/{lang}/2026-10-11-csv-export.md"))
    assert b.date == "2026-10-11" and len(b.steps) == 3
    assert (b.status_date, b.check.splitlines()[0].split(":")[0]) == ("2026-10-12", {"en": "Account", "ru": "Аккаунт"}[lang])
    forks = briefs.parse_forks(b.decisions)
    assert len(forks) == 2 and forks[0].options[0] == forks[0].proposed
    assert b.outside


def test_fixture_briefs_say_the_same():
    en, ru = (briefs.parse_brief(read(f"briefs/{lang}/2026-10-11-csv-export.md")) for lang in i18n.LANGS)
    assert (en.date, en.status_date, len(en.decisions)) == (ru.date, ru.status_date, len(ru.decisions))
    assert [len(f.options) for f in briefs.parse_forks(en.decisions)] == \
        [len(f.options) for f in briefs.parse_forks(ru.decisions)]


# --- forks ---

def test_english_fork_fields():
    line = "2. Question: Keep history? Proposed: yes, 30 days. Why: enough to debug. Options: yes, 30 days | no | forever."
    assert briefs.parse_forks([line]) == [briefs.Fork("Keep history?", "yes, 30 days", "enough to debug",
                                                      ["yes, 30 days", "no", "forever"])]


def test_russian_fork_fields():
    forks = briefs.parse_forks(["1. Без вопроса. Почему: так.", FORK_RU])
    assert forks == [briefs.Fork("Хранить ли историю?", "да, 30 дней", "хватит для разбора",
                                 ["да, 30 дней", "нет", "навсегда"])]


def test_plain_decisions_are_not_forks():
    assert briefs.parse_forks(["1. One file per user. Why: simple.", "1. Без вопроса. Почему: так."]) == []


@pytest.mark.parametrize("fork, proposed_only, others", [
    ("1. Question: Q? Proposed: A.", "1. Question: Q? Proposed: B. Options: A | C.", ""),
    ("1. Вопрос: Q? Предлагаю: A.", "1. Вопрос: Q? Предлагаю: B. Варианты: A | C.", ""),
])
def test_fork_defaults_and_proposed_first(fork, proposed_only, others):
    f = briefs.parse_forks([fork])[0]
    assert f.reason == others and f.options == ["A"]
    assert briefs.parse_forks([proposed_only])[0].options == ["B", "A", "C"]


def test_proposed_repeated_in_options_is_listed_once():
    assert briefs.parse_forks(["1. Question: Q? Proposed: A. Options: A | B."])[0].options == ["A", "B"]


@pytest.mark.parametrize("lang, label", [("en", "Proposed"), ("ru", "Предлагаю")])
def test_fork_without_proposed_raises_in_current_language(lang, label):
    i18n.use(lang)
    for line in ("1. Question: Q?", "1. Вопрос: Q?", "1. Question: Q? Proposed: ."):
        with pytest.raises(ValueError, match=label):
            briefs.parse_forks([line])


# --- the brief ---

BRIEF = ("# Pain\n\nDate: 2026-10-21. Status: draft.\n\n## 4. Decisions\n1. So.\n\n## 9. How we check\nSteps.\n\n"
         "## 10. Steps\ntext without a number\n1. First\n3. \n- marker\n10. Tenth\n")
BRIEF_RU = ("# Боль\n\nДата: 2026-10-21. Статус: черновик.\n\n## 4. Решения\n1. Так.\n\n## 9. Как проверим\nШаги.\n\n"
            "## 10. Карточки\nтекст без номера\n1. Первый\n3. \n- маркер\n10. Десятый\n")


@pytest.mark.parametrize("text, steps, status", [(BRIEF, ["First", "Tenth"], "draft"),
                                                  (BRIEF_RU, ["Первый", "Десятый"], "черновик")])
def test_steps_ignore_garbage(text, steps, status):
    b = briefs.parse_brief(text)
    assert b.steps == steps and briefs.require_steps(b) == b.steps
    assert (b.date, b.status, b.status_date, b.check) == ("2026-10-21", status, None, {BRIEF: "Steps.", BRIEF_RU: "Шаги."}[text])


@pytest.mark.parametrize("lang, words", [("en", "no steps"), ("ru", "нет шагов")])
def test_require_steps_empty_raises(lang, words):
    i18n.use(lang)
    empty_ten = BRIEF.split("## 10. Steps")[0] + "## 10. Steps\ntext without a number\n- marker\n"
    with pytest.raises(ValueError, match=words):
        briefs.require_steps(briefs.parse_brief(empty_ten))


def test_section_ten_found_by_number():
    assert briefs.parse_brief(BRIEF.replace("## 10. Steps", "## 10. Карточки")).steps == ["First", "Tenth"]
    assert briefs.parse_brief(BRIEF_RU.replace("## 10. Карточки", "## 10. Steps")).steps == ["Первый", "Десятый"]


def test_status_line_may_mix_languages():
    mixed = BRIEF.replace("Date: 2026-10-21. Status: draft.", "Дата: 2026-10-21. Status: approved 2026-10-22.")
    b = briefs.parse_brief(mixed)
    assert (b.date, b.status, b.status_date) == ("2026-10-21", "approved", "2026-10-22")


@pytest.mark.parametrize("lang, words", [("en", "status"), ("ru", "статус")])
def test_brief_without_status_raises_in_current_language(lang, words):
    i18n.use(lang)
    with pytest.raises(ValueError, match=words):
        briefs.parse_brief("# Pain\n\n## 10. Steps\n1. One\n")


def test_outside_line_in_both_languages():
    assert briefs.parse_brief(BRIEF + "\nOutside the run: owner — check.\n").outside == "owner — check."
    assert briefs.parse_brief(BRIEF_RU + "\nВне рана: владелец — проверить.\n").outside == "владелец — проверить."
    assert briefs.parse_brief(BRIEF).outside is None


# --- prompts ---

@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("kind", KINDS)
def test_prompts_exist(lang, kind):
    text = prompts.load("default", kind, lang)
    if kind == "brief-again":
        assert "{brief}" in text
        return
    assert "{result}" in text and "{root}" in text and "—" in text
    if kind == "brief":
        assert "{answers}" in text and FORK_LABEL[lang] in text


@pytest.mark.parametrize("kind", (*KINDS, "brief-template"))
def test_prompts_keep_the_line_layout_of_the_other_language(kind):
    en, ru = (prompts.load("default", kind, lang).splitlines() for lang in i18n.LANGS)
    assert [bool(line.strip()) for line in en] == [bool(line.strip()) for line in ru]


def test_english_prompts_have_no_cyrillic():
    texts = {kind: prompts.load("default", kind, "en") for kind in (*KINDS, "brief-template")}
    assert [kind for kind, text in texts.items() if CYRILLIC.search(text)] == []


def test_unknown_prompt_language_raises():
    with pytest.raises(i18n.LangError, match="de"):
        prompts.load("default", "brief", "de")


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_template_has_ten_sections_and_sits_in_the_brief_prompt(lang):
    text = prompts.template(lang)
    assert all(f"## {n}." in text for n in range(1, 11)) and FORK_LABEL[lang] in text
    assert text.strip() in prompts.load("default", "brief", lang)


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_template_brief_parses(lang):
    """A brief written by the template passes the parser of the same language."""
    text = prompts.template(lang).replace("YYYY-MM-DD", "2026-10-11")
    b = briefs.parse_brief(text)
    assert b.date == "2026-10-11" and b.outside and len(b.steps) == 2
    assert [f.proposed for f in briefs.parse_forks(b.decisions)] == [{"en": "<answer>", "ru": "<ответ>"}[lang]]


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_brief_prompt_commit_and_result_first_and_last(lang):
    text = prompts.load("default", "brief", lang)
    lines = text.strip().splitlines()
    assert "{brief}" not in text and "{brief}" in prompts.load("default", "brief-again", lang)
    assert "docs(brief)" in lines[3] and "blocked" in lines[3] and "{result}" in lines[4]
    assert "docs(brief)" in lines[-1] and "{result}" in lines[-1]


def _nod_lines(kind: str, lang: str) -> list[str]:
    return [ln.strip("`") for ln in rendered(kind, lang).splitlines() if ln.startswith("`nod ")]


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("kind", ("run", "accept"))
def test_prompt_commands_parse(lang, kind):
    lines = _nod_lines(kind, lang)
    assert len(lines) == {"run": 3, "accept": 2}[kind]
    if kind == "run":
        progress = next(ln for ln in lines if " run progress " in ln).replace("--contracts-done N", "--contracts-done 1")
        args = build_parser().parse_args(shlex.split(progress)[1:])
        assert (args.root, args.id, args.contracts_done) == ("/repo", "run-1", 1)
    ask = next(ln for ln in lines if " decision ask " in ln)
    args = build_parser().parse_args(shlex.split(ask)[1:])
    assert (args.kind, args.card, args.proposed, args.option) == ("owner-action", "c-1", "done", ["done", "postpone"])
    show = next(ln for ln in lines if " decision list " in ln)
    listed = build_parser().parse_args(shlex.split(show)[1:])
    assert listed.all and listed.json and listed.root == "/repo"


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("kind", ("run", "accept"))
def test_prompts_name_the_canonical_owner_answers(lang, kind):
    text = rendered(kind, lang)
    assert "Ответ `done`" in text or "Answer `done`" in text
    assert "`postpone`" in text and "«сделано»" not in text and "«отложить»" not in text


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_accept_prompt_lists_every_result(lang):
    text = rendered("accept", lang)
    assert all(f'"{value}"' in text for value in model.ACCEPT_RESULTS)
    assert all(f"`{value}`" in text for value in model.ACCEPT_RESULTS)


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_accept_prompt_frames_start_empty(lang):
    """An empty frame path made the acceptance unverified: the example is an empty list and a filled item."""
    text = rendered("accept", lang)
    assert "`frames = []`" in text and 'path = ""' not in text
    assert '{ path = "docs/briefs/shot.png", caption = "…" }' in text


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_brief_prompt_keeps_blocked_and_names_owner_action(lang):
    text = prompts.load("default", "brief", lang)
    assert "blocked =" in text and "owner-action" in text
    assert "--kind owner-action" not in text and ".nod/cards/" in text


def test_brief_prompt_forbids_decision_ask_only_with_blocked():
    en = prompts.load("default", "brief", "en")
    assert "If you wrote `blocked`, do not also run `decision ask`: there would be two decisions" in en
    ru = prompts.load("default", "brief", "ru")
    assert "Если ты записал `blocked`, команду `decision ask` не запускай: решений станет два" in ru
    assert "Команду `decision ask` в брифе не запускай" not in ru


@pytest.mark.parametrize("kind", ("brief", "run", "accept"))
def test_english_prompts_name_a_test_environment(kind):
    """The Russian word for a test environment has no word-for-word English form: the prompt says what it is."""
    text = prompts.load("default", kind, "en")
    assert "a test environment that is down" in text and not re.search(r"\bstand\b", text)


@pytest.mark.parametrize("lang, no_title, no_date", [("en", "no title", "no brief date"),
                                                      ("ru", "не найдено название", "не найдена дата брифа")])
def test_brief_without_title_or_date_raises_in_current_language(lang, no_title, no_date):
    i18n.use(lang)
    with pytest.raises(ValueError, match=no_title):
        briefs.parse_brief(BRIEF.replace("# Pain\n", ""))
    with pytest.raises(ValueError, match=no_date):
        briefs.parse_brief(BRIEF.replace("Date: 2026-10-21.", "Date: soon."))


ALLOWED = {"brief": default.ALLOWED_BRIEF, "run": default.ALLOWED_RUN, "accept": default.ALLOWED_ACCEPT}
BASH_RULE = re.compile(r"Bash\(([^)]*)\)")
ALLOWLIST_LINE = {"en": "The default allowlist lets Bash run these commands, one command per call: ",
                  "ru": "Список разрешений по умолчанию даёт Bash запускать эти команды, по одной за вызов: "}


def _rules(kind: str) -> list[str]:
    """The Bash commands the adapter allows the agent of `kind`, `python -m the_nod` aside: the prompt names `nod`."""
    return [rule for rule in BASH_RULE.findall(ALLOWED[kind])
            if not rule.startswith(("python -m the_nod", "python3 -m the_nod"))]


def test_allowlist_takes_python3_too():
    """Stock macOS and Ubuntu have `python3` only: the tests and the core run under that name as well."""
    for kind in ("brief", "run", "accept"):
        assert "Bash(python3 -m the_nod *)" in ALLOWED[kind]
    for kind in ("run", "accept"):
        assert "Bash(python3 -m pytest)" in ALLOWED[kind] and "Bash(python3 -m pytest *)" in ALLOWED[kind]
    assert "python3 -m pytest" not in ALLOWED["brief"]


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("kind", ("brief", "run", "accept"))
def test_prompts_name_the_allowed_bash_commands(lang, kind):
    """The field test: an agent ran `cd <root>; … git log` and `git -C <root> status`, got two denials and stopped.

    The prompt names every command the allowlist lets through and forbids `cd` and `git -C`.
    """
    text = prompts.load("default", kind, lang)
    assert "`cd`" in text and "`git -C`" in text and "Read, Grep" in text
    # The list is what the default commands allow: a manifest with its own command may allow more.
    assert ALLOWLIST_LINE[lang] in text
    for rule in _rules(kind):
        shown = rule.removesuffix(" *")
        assert (f"`{shown}`" if shown == rule else f"`{shown} ") in text, rule
    if "Bash(python -m pytest *)" not in ALLOWED[kind]:
        assert "`python -m pytest" not in text and "`python3 -m pytest" not in text
    if "Bash(git commit *)" not in ALLOWED[kind]:
        assert "`git commit" not in text


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("kind", KINDS)
def test_prompts_leave_commit_attribution_to_the_user(lang, kind):
    """Co-Authored-By lines follow the user's Claude Code settings: no prompt asks for them or forbids them."""
    assert "Co-Authored-By" not in prompts.load("default", kind, lang)
