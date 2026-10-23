"""Interface language: resolution, catalogs, and the CLI following `lang` and NOD_LANG."""
import json
import re
import string
from pathlib import Path

import pytest

from the_nod import harness, i18n
from the_nod.cli import main
from the_nod.store import Store

CYRILLIC = re.compile(r"[Ѐ-ӿ]")
PACKAGE = Path(__file__).parent.parent / "the_nod"
KEY = re.compile(r"[a-z]+\.[a-z0-9_]+")
USED_KEY = re.compile(r"""\bt\(\s*["']([a-z_.0-9]+)["']""")


def fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


def init(repo, capsys) -> None:
    assert main(["--root", str(repo), "init"]) == 0
    capsys.readouterr()


def set_lang(repo, value: str) -> None:
    """Replaces the `lang` line of an initialized manifest."""
    path = repo / ".nod" / "harness.toml"
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r'(?m)^lang = ".*"$', f'lang = "{value}"', text), encoding="utf-8")


# --- catalogs ---

def test_catalogs_have_same_keys_and_placeholders():
    en, ru = i18n.catalog("en"), i18n.catalog("ru")
    assert en.keys() == ru.keys()
    for key in en:
        assert fields(en[key]) == fields(ru[key]), key


def test_english_catalog_has_no_cyrillic():
    assert [k for k, v in i18n.catalog("en").items() if CYRILLIC.search(v)] == []


def test_keys_and_placeholders_are_plain_names():
    for lang in i18n.LANGS:
        for key, text in i18n.catalog(lang).items():
            assert KEY.fullmatch(key), key
            assert all(name.isidentifier() for name in fields(text)), key


def test_every_key_used_in_code_exists():
    used = {key for path in PACKAGE.rglob("*.py") for key in USED_KEY.findall(path.read_text(encoding="utf-8"))}
    assert used and sorted(used - i18n.catalog("en").keys()) == []


QUOTED_KEY = re.compile(r"""["']([a-z]+\.[a-z0-9_]+)["']""")


@pytest.mark.parametrize("area", ["review", "doctor", "mcp", "autostart"])
def test_every_key_of_a_late_area_is_used_in_code(area):
    """A key nobody asks for is a text nobody sees: the areas of the review, doctor, MCP and autostart stay free of them."""
    module = __import__(f"the_nod.i18n.en.{area}", fromlist=["MESSAGES"])
    quoted = {key for path in PACKAGE.rglob("*.py") if "i18n" not in path.parts
              for key in QUOTED_KEY.findall(path.read_text(encoding="utf-8"))}
    assert sorted(set(module.MESSAGES) - quoted) == []


def test_late_areas_are_listed_in_both_catalogs():
    from the_nod.i18n import en, ru
    assert {"review", "doctor", "mcp", "autostart"} <= set(en.AREAS) and en.AREAS == ru.AREAS


def test_duplicate_key_across_areas_fails():
    with pytest.raises(ValueError, match="cli.error"):
        i18n.merge([("first", {"cli.error": "a"}), ("second", {"cli.error": "b"})])
    assert i18n.merge([("first", {"a.x": "1"}), ("second", {"a.y": "2"})]) == {"a.x": "1", "a.y": "2"}


def test_duplicate_key_across_area_modules_fails(tmp_path, monkeypatch):
    package = tmp_path / "fake_catalog"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "one.py").write_text('MESSAGES = {"core.same": "1"}\n', encoding="utf-8")
    (package / "two.py").write_text('MESSAGES = {"core.same": "2"}\n', encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    assert i18n.collect("fake_catalog", ("one",)) == {"core.same": "1"}
    with pytest.raises(ValueError, match="core.same"):
        i18n.collect("fake_catalog", ("one", "two"))


def test_catalog_packages_list_their_areas():
    from the_nod.i18n import en, ru
    assert en.AREAS == ru.AREAS and "core" in en.AREAS


# --- resolution and the current language ---

def test_env_wins_over_manifest():
    assert i18n.resolve("ru", env={"NOD_LANG": "en"}) == "en"
    assert i18n.resolve("ru", env={}) == "ru" and i18n.resolve(None, env={}) == "en"


def test_empty_env_falls_back_to_manifest():
    assert i18n.resolve("ru", env={"NOD_LANG": ""}) == "ru"
    assert i18n.resolve(None, env={"NOD_LANG": "  "}) == "en"


def test_unknown_env_lang_raises_lang_error():
    with pytest.raises(i18n.LangError, match="NOD_LANG=de: unknown language, use en or ru"):
        i18n.resolve(None, env={"NOD_LANG": "de"})
    assert issubclass(i18n.LangError, ValueError)


def test_resolve_reads_process_env_by_default(monkeypatch):
    monkeypatch.setenv("NOD_LANG", "ru")
    assert i18n.resolve() == "ru"


def test_use_current_and_t():
    assert i18n.current() == "en" and i18n.t("cli.error", message="x") == "error: x"
    i18n.use("ru")
    assert i18n.current() == "ru" and i18n.t("cli.error", message="x") == "ошибка: x"
    with pytest.raises(i18n.LangError):
        i18n.use("de")
    assert i18n.current() == "ru"


def test_missing_key_fails_loudly():
    with pytest.raises(KeyError):
        i18n.t("cli.no_such_key")


# --- the CLI ---

def test_bad_env_lang_exits_2_in_english(capsys, monkeypatch):
    monkeypatch.setenv("NOD_LANG", "de")
    assert main(["status"]) == 2
    assert "error: NOD_LANG=de: unknown language, use en or ru" in capsys.readouterr().err
    assert i18n.current() == "en"


def test_bad_env_lang_is_english_after_a_russian_call(repo, capsys, monkeypatch):
    init(repo, capsys)
    set_lang(repo, "ru")
    main(["--root", str(repo), "card", "show", "c-nope"])
    capsys.readouterr()
    monkeypatch.setenv("NOD_LANG", "de")
    assert main(["--root", str(repo), "status"]) == 2
    assert not CYRILLIC.search(capsys.readouterr().err)


def test_manifest_lang_ru_switches_cli(repo, capsys):
    init(repo, capsys)
    set_lang(repo, "ru")
    assert main(["--root", str(repo), "card", "show", "c-nope"]) == 2
    err = capsys.readouterr().err
    assert CYRILLIC.search(err) and err.startswith("ошибка: ")


def test_default_is_english(repo, capsys):
    init(repo, capsys)
    assert main(["--root", str(repo), "card", "show", "c-nope"]) == 2
    err = capsys.readouterr().err
    assert not CYRILLIC.search(err) and err.startswith("error: ")


def test_env_overrides_manifest_in_cli(repo, capsys, monkeypatch):
    init(repo, capsys)
    set_lang(repo, "ru")
    monkeypatch.setenv("NOD_LANG", "en")
    assert main(["--root", str(repo), "card", "show", "c-nope"]) == 2
    assert not CYRILLIC.search(capsys.readouterr().err)


def test_each_call_starts_from_env_language(repo, tmp_path, capsys):
    """One process, two states (as in the MCP server): the second call does not inherit `ru`."""
    init(repo, capsys)
    set_lang(repo, "ru")
    main(["--root", str(repo), "card", "show", "c-nope"])
    capsys.readouterr()
    assert main(["--root", str(tmp_path / "nowhere"), "status", "--no-sync"]) == 2
    assert capsys.readouterr().err == "error: no state: run nod init\n"


def test_bad_manifest_lang_is_harness_error(repo, capsys):
    init(repo, capsys)
    set_lang(repo, "fr")
    assert main(["--root", str(repo), "status", "--no-sync"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "lang" in err and "fr" in err and "Traceback" not in err
    with pytest.raises(harness.HarnessError, match="lang"):
        harness.load(Store(repo / ".nod"))


def test_read_lang(tmp_path):
    state = tmp_path / ".nod"
    state.mkdir()
    assert harness.read_lang(state) is None
    manifest = state / "harness.toml"
    manifest.write_text('adapter = "default"\n', encoding="utf-8")
    assert harness.read_lang(state) is None
    manifest.write_text('lang = "ru"\n', encoding="utf-8")
    assert harness.read_lang(state) == "ru"
    manifest.write_text("lang = [\n", encoding="utf-8")
    assert harness.read_lang(state) is None
    for bad in ('lang = "fr"\n', "lang = 1\n"):
        manifest.write_text(bad, encoding="utf-8")
        with pytest.raises(harness.HarnessError, match="lang"):
            harness.read_lang(state)


def test_harness_lang_field(tmp_path):
    s = Store(tmp_path / ".nod")
    (s.root / "harness.toml").write_text('lang = "ru"\n', encoding="utf-8")
    assert harness.load(s).lang == "ru"
    (s.root / "harness.toml").write_text('adapter = "default"\n', encoding="utf-8")
    assert harness.load(s).lang == "en"


def test_snapshot_carries_lang(repo, capsys):
    init(repo, capsys)
    assert main(["--root", str(repo), "--json", "status", "--no-sync"]) == 0
    assert json.loads(capsys.readouterr().out)["lang"] == "en"
    set_lang(repo, "ru")
    assert main(["--root", str(repo), "--json", "status", "--no-sync"]) == 0
    assert json.loads(capsys.readouterr().out)["lang"] == "ru"
    assert json.loads((repo / ".nod" / "state.json").read_text(encoding="utf-8"))["lang"] == "ru"


def test_init_template_follows_lang(repo, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("NOD_LANG", "ru")
    init(repo, capsys)
    text = (repo / ".nod" / "harness.toml").read_text(encoding="utf-8")
    comments = [line for line in text.splitlines() if line.startswith("#")]
    assert 'lang = "ru"' in text.splitlines() and all(CYRILLIC.search(c) for c in comments[:3])
    assert harness.load(Store(repo / ".nod")).lang == "ru"


def test_init_template_english_by_default(repo, capsys):
    init(repo, capsys)
    text = (repo / ".nod" / "harness.toml").read_text(encoding="utf-8")
    assert 'lang = "en"' in text.splitlines() and not CYRILLIC.search(text)
    assert harness.load(Store(repo / ".nod")).lang == "en"


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_harness_template_is_a_valid_manifest(lang):
    i18n.use(lang)
    data = __import__("tomllib").loads(i18n.t("init.harness_template", lang=lang))
    assert harness.validate(data).lang == lang and "{answers}" in i18n.t("init.harness_template", lang=lang)


def test_help_follows_env_only(repo, capsys, monkeypatch):
    init(repo, capsys)
    set_lang(repo, "ru")
    with pytest.raises(SystemExit):
        main(["--root", str(repo), "card", "--help"])
    assert not CYRILLIC.search(capsys.readouterr().out)
    monkeypatch.setenv("NOD_LANG", "ru")
    with pytest.raises(SystemExit):
        main(["--root", str(repo), "card", "--help"])
    assert CYRILLIC.search(capsys.readouterr().out)
