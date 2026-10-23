"""`nod import markdown`: a `##` list becomes backlog cards."""
import json
import re
import subprocess

import pytest

from the_nod.cli import main
from the_nod.importers import markdown
from the_nod.store import Store

CYRILLIC = re.compile(r"[Ѐ-ӿ]")
PLAN = """\
# Tidepool

Notes before the first card are ignored.

## Export habits to CSV
Users ask.

## Weekly email digest
Every Monday.
- one
- two

## Dark mode for the habit grid
"""


def run(repo, *args, capsys):
    code = main(["--root", str(repo), *args])
    out = capsys.readouterr()
    return code, out.out, out.err


def setup(repo, capsys, text=PLAN, name="plan.md"):
    """An initialized state and a markdown file next to the repo; returns the file path."""
    assert run(repo, "init", capsys=capsys)[0] == 0
    path = repo.parent / name
    path.write_text(text, encoding="utf-8")
    return path


def commits(repo) -> list[str]:
    out = subprocess.run(["git", "log", "--format=%s"], cwd=repo, capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout
    return out.splitlines()


def titles(repo) -> list[str]:
    store = Store(repo / ".nod")
    by_id = {c.id: c for c in store.cards()}
    return [by_id[i].title for i in store.order()]


# --- parse ---

def test_parse_headings_and_bodies():
    assert markdown.parse("# Tidepool\nintro\n## Export habits to CSV\nUsers ask.\n\n## Dark mode ##\n") == [
        ("Export habits to CSV", "Users ask."), ("Dark mode", "")]


def test_parse_without_headings_gives_nothing():
    assert markdown.parse("") == []
    assert markdown.parse("# Title\njust text\n### Not a card\n") == []


def test_parse_keeps_deeper_headings_and_lists_in_the_body():
    text = "## Card\nintro\n### Details\n- a\n- b\n#hashtag\n"
    assert markdown.parse(text) == [("Card", "intro\n### Details\n- a\n- b\n#hashtag")]


def test_parse_skips_empty_titles_and_their_bodies():
    text = "## First\none\n## \nlost\n##\nalso lost\n## ###\nstill lost\n## Last\ntwo\n"
    assert markdown.parse(text) == [("First", "one"), ("Last", "two")]


@pytest.mark.parametrize("heading,title", [
    ("## Dark mode ##", "Dark mode"),
    ("## Dark mode ###   ", "Dark mode"),
    ("##   Padded   ", "Padded"),
    ("## Port to C#", "Port to C#"),
    ("## Issue #12", "Issue #12"),
    ("##\tTabbed", "Tabbed"),
])
def test_parse_title_cleanup(heading, title):
    assert markdown.parse(heading + "\n") == [(title, "")]


def test_parse_long_title_is_cut_and_kept_in_full_in_the_body():
    full = "word " * 40 + "end"
    [(title, body)] = markdown.parse(f"## {full}\nDetails.\n")
    assert len(title) <= 120 and full.startswith(title) and title == title.rstrip()
    assert body == f"{full}\n\nDetails."
    [(title, body)] = markdown.parse(f"## {full}\n")
    assert body == full
    [(title, body)] = markdown.parse("## " + "x" * 120 + "\n")
    assert title == "x" * 120 and body == ""


def test_parse_a_top_level_heading_ends_the_card():
    text = "## One\nbody\n# Another part\nnot a card body\n## Two\n"
    assert markdown.parse(text) == [("One", "body"), ("Two", "")]


def test_parse_fenced_code_is_plain_body():
    text = "## Setup\n```bash\n# install\n## not a card\npip install nod\n```\nafter\n## Next\n"
    assert markdown.parse(text) == [
        ("Setup", "```bash\n# install\n## not a card\npip install nod\n```\nafter"), ("Next", "")]
    assert markdown.parse("## A\n~~~\n## B\n~~~\n## C\n") == [("A", "~~~\n## B\n~~~"), ("C", "")]
    # A longer fence is not closed by a shorter one; a closing fence has no text after it.
    assert markdown.parse("## A\n````\n```\n## B\n````\n## C\n") == [("A", "````\n```\n## B\n````"), ("C", "")]
    assert markdown.parse("## A\n```\n```x\n## B\n```\n## C\n") == [("A", "```\n```x\n## B\n```"), ("C", "")]


def test_parse_backtick_fence_with_a_backtick_in_the_info_string_is_not_a_fence():
    # CommonMark: this is inline code, not a fence, so the next `##` is a heading.
    assert markdown.parse("## A\n```x``` y\n## B\n") == [("A", "```x``` y"), ("B", "")]
    assert markdown.parse("## A\n``` `x`\ntext\n```\n## B\n") == [("A", "``` `x`\ntext\n```"), ("B", "")]
    # The same text after a tilde fence is allowed.
    assert markdown.parse("## A\n~~~ `x`\n## B\n~~~\n## C\n") == [("A", "~~~ `x`\n## B\n~~~"), ("C", "")]


def test_parse_unclosed_fence_does_not_swallow_later_headings():
    text = "## A\n```bash\n# note\nbody\n## B\ntext\n## C\nlast\n"
    # The opener is plain text; what follows is read as usual: `# note` ends A, `##` start cards.
    assert markdown.parse(text) == [("A", "```bash"), ("B", "text"), ("C", "last")]
    assert markdown.parse("## A\n````\n```\n## B\n") == [("A", "````\n```"), ("B", "")]
    assert markdown.parse("## A\n~~~\n## B\n") == [("A", "~~~"), ("B", "")]
    # A closed block before the stray opener still counts as code.
    text = "## A\n```\n## inside\n```\n## B\n```\n## C\n"
    assert markdown.parse(text) == [("A", "```\n## inside\n```"), ("B", "```"), ("C", "")]


def test_parse_line_endings():
    assert markdown.parse("## A\r\nline\r\n\r\n## B\rtext\r") == [("A", "line"), ("B", "text")]


def test_parse_does_not_split_on_exotic_separators():
    assert markdown.parse("## A\nx\u2028## not a heading\ny\x0c\n") == [("A", "x\u2028## not a heading\ny")]


# --- the command ---

def test_import_creates_backlog_cards_in_order(repo, capsys):
    path = setup(repo, capsys)
    existing = run(repo, "card", "add", "Existing", capsys=capsys)[1].strip()
    code, out, err = run(repo, "import", "markdown", "--from", str(path), capsys=capsys)
    assert code == 0 and err == "" and out.strip() == "imported cards: 3"
    assert titles(repo) == ["Existing", "Export habits to CSV", "Weekly email digest",
                            "Dark mode for the habit grid"]
    store = Store(repo / ".nod")
    assert store.order()[0] == existing
    cards = [store.load_card(i) for i in store.order()[1:]]
    assert {c.status for c in cards} == {"backlog"} and {c.source for c in cards} == {"import"}
    assert [c.body for c in cards] == ["Users ask.", "Every Monday.\n- one\n- two", ""]
    assert all(c.created for c in cards) and len({c.created for c in cards}) == 1
    order = (repo / ".nod" / "order.md").read_text(encoding="utf-8")
    assert [line.split()[0] for line in order.splitlines()[2:]] == store.order()


def test_import_skips_existing_titles(repo, capsys):
    path = setup(repo, capsys)
    run(repo, "card", "add", "export HABITS to csv", capsys=capsys)
    code, out, _ = run(repo, "import", "markdown", "--from", str(path), capsys=capsys)
    assert code == 0
    assert out.splitlines() == ["skipped: Export habits to CSV — already a card", "imported cards: 2"]
    assert titles(repo) == ["export HABITS to csv", "Weekly email digest", "Dark mode for the habit grid"]
    # A second run finds everything in place and writes nothing.
    before = commits(repo)
    code, out, err = run(repo, "import", "markdown", "--from", str(path), capsys=capsys)
    assert code == 0 and out.splitlines()[-1] == "imported cards: 0" and len(out.splitlines()) == 4
    assert err == "" and commits(repo) == before  # headings were found: no "no headings" hint


def test_import_skips_titles_repeated_in_the_file(repo, capsys):
    path = setup(repo, capsys, "## Same\nfirst\n## same\nsecond\n")
    code, out, _ = run(repo, "import", "markdown", "--from", str(path), capsys=capsys)
    assert code == 0 and out.splitlines() == ["skipped: same — already a card", "imported cards: 1"]
    store = Store(repo / ".nod")
    assert [(c.title, c.body) for c in store.cards()] == [("Same", "first")]


def test_import_closed_card_still_counts(repo, capsys):
    path = setup(repo, capsys, "## Old work\n")
    cid = run(repo, "card", "add", "Old work", capsys=capsys)[1].strip()
    run(repo, "card", "close", cid, capsys=capsys)
    _, out, _ = run(repo, "import", "markdown", "--from", str(path), capsys=capsys)
    assert out.splitlines() == ["skipped: Old work — already a card", "imported cards: 0"]


def test_import_dry_run_writes_nothing(repo, capsys):
    path = setup(repo, capsys)
    run(repo, "card", "add", "Weekly email digest", capsys=capsys)
    head, log = commits(repo)[0], commits(repo)
    files = sorted(p.name for p in (repo / ".nod").rglob("*") if p.is_file())
    order = (repo / ".nod" / "order.md").read_bytes()
    code, out, _ = run(repo, "import", "markdown", "--from", str(path), "--dry-run", capsys=capsys)
    assert code == 0
    assert out.splitlines() == [
        "would import: Export habits to CSV", "skipped: Weekly email digest — already a card",
        "would import: Dark mode for the habit grid", "dry run: would import cards: 2"]
    assert commits(repo) == log and commits(repo)[0] == head
    assert sorted(p.name for p in (repo / ".nod").rglob("*") if p.is_file()) == files
    assert (repo / ".nod" / "order.md").read_bytes() == order
    assert len(Store(repo / ".nod").cards()) == 1


def test_import_json(repo, capsys):
    path = setup(repo, capsys)
    run(repo, "card", "add", "Weekly email digest", capsys=capsys)
    code, out, _ = run(repo, "--json", "import", "markdown", "--from", str(path), "--dry-run", capsys=capsys)
    assert code == 0 and json.loads(out) == {
        "would_import": ["Export habits to CSV", "Dark mode for the habit grid"],
        "skipped": ["Weekly email digest"]}
    code, out, _ = run(repo, "import", "markdown", "--from", str(path), "--json", capsys=capsys)
    assert code == 0 and json.loads(out) == {"imported": 2, "skipped": ["Weekly email digest"]}
    code, out, _ = run(repo, "--json", "import", "markdown", "--from", str(path), capsys=capsys)
    assert json.loads(out)["imported"] == 0 and len(json.loads(out)["skipped"]) == 3


def test_import_one_commit(repo, capsys):
    path = setup(repo, capsys)
    before = commits(repo)
    run(repo, "import", "markdown", "--from", str(path), capsys=capsys)
    after = commits(repo)
    assert after[1:] == before and after[0] == "state: import markdown plan.md"
    changed = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=repo,
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout.split()
    assert len([p for p in changed if p.startswith(".nod/cards/")]) == 3 and ".nod/order.md" in changed
    assert subprocess.run(["git", "status", "--porcelain", "--", ".nod"], cwd=repo, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout == ""


def test_import_refused_to_agent(repo, capsys, monkeypatch):
    path = setup(repo, capsys)
    before = commits(repo)
    monkeypatch.setenv("NOD_AGENT", "1")
    for extra in ([], ["--dry-run"]):
        code, out, err = run(repo, "import", "markdown", "--from", str(path), *extra, capsys=capsys)
        assert code == 2 and out == "" and "not available to the driver's agent" in err
    assert Store(repo / ".nod").cards() == [] and commits(repo) == before


def test_import_missing_file(repo, capsys, tmp_path):
    setup(repo, capsys)
    missing = tmp_path / "nowhere.md"
    code, out, err = run(repo, "import", "markdown", "--from", str(missing), capsys=capsys)
    assert code == 2 and out == "" and err == f"error: file not found: {missing}\n"
    code, _, err = run(repo, "import", "markdown", "--from", str(tmp_path), capsys=capsys)
    assert code == 2 and f"file not found: {tmp_path}" in err


def test_import_not_utf8(repo, capsys):
    path = setup(repo, capsys)
    path.write_bytes("## Заголовок\n".encode("cp1251"))
    code, out, err = run(repo, "import", "markdown", "--from", str(path), capsys=capsys)
    assert code == 2 and out == "" and "not valid UTF-8" in err and str(path) in err
    assert "Traceback" not in err and Store(repo / ".nod").cards() == []


NO_HEADINGS = {
    "en": ('no "## " headings in {path}', "imported cards: 0", "dry run: would import cards: 0"),
    "ru": ("нет заголовков «## » в {path}", "импортировано карточек: 0",
           "пробный прогон: будет импортировано карточек: 0"),
}


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_import_file_without_headings_says_so(repo, capsys, monkeypatch, lang):
    template, imported, dry = NO_HEADINGS[lang]
    monkeypatch.setenv("NOD_LANG", lang)
    path = setup(repo, capsys, "# Tidepool\n\nJust notes.\n### Not a card\n")
    before = commits(repo)
    hint = template.format(path=path) + "\n"
    code, out, err = run(repo, "import", "markdown", "--from", str(path), capsys=capsys)
    assert (code, out, err) == (0, imported + "\n", hint)
    code, out, err = run(repo, "import", "markdown", "--from", str(path), "--dry-run", capsys=capsys)
    assert (code, out, err) == (0, dry + "\n", hint)
    # The hint goes to stderr, so the JSON on stdout stays clean.
    code, out, err = run(repo, "--json", "import", "markdown", "--from", str(path), capsys=capsys)
    assert code == 0 and json.loads(out) == {"imported": 0, "skipped": []} and err == hint
    assert commits(repo) == before and Store(repo / ".nod").cards() == []
    assert bool(CYRILLIC.search(template)) == (lang == "ru")  # the path may hold any letters


def test_import_empty_file_says_so(repo, capsys):
    path = setup(repo, capsys, "")
    code, out, err = run(repo, "import", "markdown", "--from", str(path), capsys=capsys)
    assert (code, out, err) == (0, "imported cards: 0\n", f'no "## " headings in {path}\n')


def test_import_requires_from(repo, capsys):
    setup(repo, capsys)
    with pytest.raises(SystemExit) as stop:
        main(["--root", str(repo), "import", "markdown"])
    assert stop.value.code == 2 and "--from" in capsys.readouterr().err


def test_import_reads_a_bom_and_windows_line_ends(repo, capsys):
    path = setup(repo, capsys)
    path.write_bytes(b"\xef\xbb\xbf# Tidepool\r\n## Export habits to CSV\r\nUsers ask.\r\n\r\n## Dark mode\r\n")
    code, out, _ = run(repo, "import", "markdown", "--from", str(path), capsys=capsys)
    assert code == 0 and out.strip() == "imported cards: 2"
    assert sorted(titles(repo)) == ["Dark mode", "Export habits to CSV"]
    bodies = {c.title: c.body for c in Store(repo / ".nod").cards()}
    assert bodies == {"Export habits to CSV": "Users ask.", "Dark mode": ""}


def test_import_card_files_survive_awkward_text(repo, capsys):
    text = ('## Fix "quotes" and C:\\path: colon\n+++\nbody with a fence line\n---\nand "quotes" \\ slash\n'
            "## Title with \u0442\u0430\u0431 \u2014 \u044e\u043d\u0438\u043a\u043e\u0434\n")
    path = setup(repo, capsys, text)
    code, _, _ = run(repo, "import", "markdown", "--from", str(path), capsys=capsys)
    assert code == 0
    cards = {c.title: c.body for c in Store(repo / ".nod").cards()}
    assert cards == {'Fix "quotes" and C:\\path: colon': '+++\nbody with a fence line\n---\nand "quotes" \\ slash',
                     "Title with \u0442\u0430\u0431 \u2014 \u044e\u043d\u0438\u043a\u043e\u0434": ""}


def test_import_long_title_is_cut_and_reimport_is_stable(repo, capsys):
    full = "Export every habit with its streaks, notes and tags to a CSV file for the spreadsheet " * 2
    path = setup(repo, capsys, f"## {full}\nDetails.\n")
    assert run(repo, "import", "markdown", "--from", str(path), capsys=capsys)[1].strip() == "imported cards: 1"
    [card] = Store(repo / ".nod").cards()
    assert len(card.title) <= 120 and full.startswith(card.title) and card.body == f"{full.strip()}\n\nDetails."
    code, out, _ = run(repo, "import", "markdown", "--from", str(path), capsys=capsys)
    assert out.splitlines()[-1] == "imported cards: 0" and len(Store(repo / ".nod").cards()) == 1


TEXTS = {
    "en": {
        "dry": ["would import: Export habits to CSV", "skipped: Weekly email digest — already a card",
                "would import: Dark mode for the habit grid", "dry run: would import cards: 2"],
        "real": ["skipped: Weekly email digest — already a card", "imported cards: 2"],
        "missing": "error: file not found: {path}",
    },
    "ru": {
        "dry": ["будет создана карточка: Export habits to CSV", "пропущено: Weekly email digest — уже есть карточка",
                "будет создана карточка: Dark mode for the habit grid", "пробный прогон: будет импортировано карточек: 2"],
        "real": ["пропущено: Weekly email digest — уже есть карточка", "импортировано карточек: 2"],
        "missing": "ошибка: файл не найден: {path}",
    },
}


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_import_texts_both_languages(repo, capsys, monkeypatch, lang):
    path = setup(repo, capsys)
    run(repo, "card", "add", "Weekly email digest", capsys=capsys)
    monkeypatch.setenv("NOD_LANG", lang)
    missing = path.parent / "nowhere.md"
    argv = ["import", "markdown", "--from", str(path)]
    texts = TEXTS[lang]

    code, out, err = run(repo, *argv, "--dry-run", capsys=capsys)
    assert (code, out.splitlines(), err) == (0, texts["dry"], "")
    code, out, err = run(repo, "import", "markdown", "--from", str(missing), capsys=capsys)
    assert (code, out, err) == (2, "", texts["missing"].format(path=missing) + "\n")
    code, out, err = run(repo, *argv, capsys=capsys)
    assert (code, out.splitlines(), err) == (0, texts["real"], "")
    for text in (*texts["dry"], *texts["real"], texts["missing"]):
        assert bool(CYRILLIC.search(text)) == (lang == "ru")


def test_import_follows_the_manifest_language(repo, capsys):
    path = setup(repo, capsys)
    manifest = repo / ".nod" / "harness.toml"
    manifest.write_text(re.sub(r'(?m)^lang = ".*"$', 'lang = "ru"', manifest.read_text(encoding="utf-8")),
                        encoding="utf-8")
    code, out, _ = run(repo, "import", "markdown", "--from", str(path), "--dry-run", capsys=capsys)
    assert code == 0 and out.splitlines()[-1] == "пробный прогон: будет импортировано карточек: 3"
    code, out, err = run(repo, "import", "markdown", "--from", str(path.parent / "nowhere.md"), capsys=capsys)
    assert code == 2 and err.startswith("ошибка: файл не найден: ")


def test_import_help_follows_env_language(repo, capsys, monkeypatch):
    setup(repo, capsys)
    with pytest.raises(SystemExit):
        main(["--root", str(repo), "import", "markdown", "--help"])
    assert not CYRILLIC.search(capsys.readouterr().out)
    monkeypatch.setenv("NOD_LANG", "ru")
    with pytest.raises(SystemExit):
        main(["--root", str(repo), "import", "markdown", "--help"])
    assert CYRILLIC.search(capsys.readouterr().out)
