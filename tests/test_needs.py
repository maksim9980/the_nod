import pytest

from the_nod import harness, i18n
from the_nod.harness import HarnessError
from the_nod.portability.needs import Needs, python_floor, validate_needs
from tests.test_harness import BASE, manifest


def test_defaults_without_section():
    n = validate_needs({})
    assert n.python == "3.13" and n.nod == "" and n.jobs == ("driver",) and n.agents == ()
    assert not hasattr(n, "mod") and not hasattr(n, "plugin_env")


def test_full_section_parsed():
    n = validate_needs({"python": "3.12", "nod": "python -m the_nod", "claude": "", "jobs": [], "agents": [".claude/agents/a.md"], "skills": ["skills/s"], "rules": []})
    assert n.python == "3.12" and n.jobs == () and n.agents == (".claude/agents/a.md",) and python_floor(n) == (3, 12)
    assert n.nod == "python -m the_nod" and n.claude == "" and n.skills == ("skills/s",)


@pytest.mark.parametrize("data, message", [
    ({"x": 1}, 'unknown key "needs.x"'), ({"python": "3"}, "python"), ({"jobs": ["cron"]}, "jobs"),
    ({"mod": "x"}, 'unknown key "needs.mod"'), ({"agents": ["../x"]}, "inside the repo"), ({"rules": ["C:/x"]}, "relative"),
    ({"skills": ["."]}, "inside the repo"), ({"agents": ["./"]}, "inside the repo"), ({"python": "3.13\n"}, "python"),
    ({"nod": 1}, "nod"), ({"skills": "a"}, "skills"), ({"plugin_env": {}}, 'unknown key "needs.plugin_env"'),
])
def test_bad_needs(data, message):
    with pytest.raises(HarnessError, match=message):
        validate_needs(data)


def test_bad_needs_section_not_table():
    with pytest.raises(HarnessError, match="needs"):
        validate_needs([])


def test_harness_load_reads_needs(tmp_path):
    h = harness.load(manifest(tmp_path, BASE + '[needs]\npython = "3.12"\n'))
    assert h.needs.python == "3.12" and harness.load(manifest(tmp_path, BASE)).needs == Needs()


@pytest.mark.parametrize("data, message", [
    ({"x": 1}, 'unknown key "needs.x"'), ({"python": 1}, '"needs.python" is not a string'),
    ({"python": "3"}, 'needs.python "3": expected a version like 3.13'),
    ({"agents": "a"}, '"needs.agents" is not a list of strings'),
    ({"jobs": ["cron"]}, 'needs.jobs: unknown job "cron", known: driver'),
    ({"rules": ["C:/x"]}, 'path needs.rules "C:/x" must be relative and inside the repo')])
def test_bad_needs_text_in_english(data, message):
    with pytest.raises(HarnessError) as error:
        validate_needs(data)
    assert str(error.value) == message


@pytest.mark.parametrize("data, message", [
    ({"x": 1}, "неизвестный ключ «needs.x»"), ({"python": 1}, "«needs.python» — не строка"),
    ({"python": "3"}, "needs.python «3»: ожидалась версия вида 3.13"),
    ({"agents": "a"}, "«needs.agents» — не список строк"),
    ({"jobs": ["cron"]}, "needs.jobs: неизвестная задача «cron», известны: driver"),
    ({"rules": ["C:/x"]}, "путь needs.rules «C:/x» должен быть относительным, внутри репы")])
def test_bad_needs_text_in_russian(data, message):
    i18n.use("ru")
    with pytest.raises(HarnessError) as error:
        validate_needs(data)
    assert str(error.value) == message


def test_bad_needs_section_not_table_text():
    with pytest.raises(HarnessError) as error:
        validate_needs([])
    assert str(error.value) == '"needs" is not a table'
    i18n.use("ru")
    with pytest.raises(HarnessError) as error:
        validate_needs([])
    assert str(error.value) == "«needs» — не таблица"
