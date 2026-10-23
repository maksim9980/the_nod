import re

import pytest

from the_nod import i18n
from the_nod.model import Suggestion
from the_nod.review import render
from the_nod.review.collect import Costly, KindStat, OpenDecision, RunRow, Stats

CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def stats(**kw) -> Stats:
    base = dict(since="2026-10-14T22:00:00", until="2026-10-21T22:00:00", runs=0, steps_done=0, stops=0, stuck=0,
                repeats=[], accepted=0, unverified=0, tokens=0, minutes=0, commits=0, asked=0, answered=0,
                median_answer_hours=None, open_over_day=[], cards=[],
                kinds=[KindStat(k, 0, 0, 0, 0, 0) for k in ("brief", "run", "accept")],
                run_rows=[], spend_rows=[], costly=[], failed_briefs=[], brief_attempts={})
    return Stats(**{**base, **kw})


def test_week_id():
    assert render.week_id("2026-10-21T22:00:00") == "2026-43"
    assert render.week_id("2027-01-01T00:00:00") == "2026-53"


def test_default_since():
    assert render.default_since("2026-10-21T22:00:00") == "2026-10-14T22:00:00"


def test_body_sections_in_order_and_empty_suggestions():
    text = render.body(stats(), [])
    heads = ["# Weekly review 2026-43 (14 Oct — 21 Oct)", "## What to improve", "## By card",
             "## By agent command", "## Most expensive", "## Least successful", "## Owner answers"]
    positions = [text.index(h) for h in heads]
    assert positions == sorted(positions)
    assert "No suggestions: the data looks normal." in text
    assert "Repeats: none" in text and "Stops: none" in text and "Stuck runs: none" in text
    assert "Failed briefs: none" in text and "median: none" in text
    assert not CYRILLIC.search(text)


def test_body_sections_in_order_in_russian():
    i18n.use("ru")
    text = render.body(stats(), [])
    heads = ["# Обзор недели 2026-43 (14 окт — 21 окт)", "## Что улучшить", "## По карточкам",
             "## По командам агентов", "## Самые дорогие", "## Самые неудачные", "## Ответы владельца"]
    positions = [text.index(h) for h in heads]
    assert positions == sorted(positions)
    assert "Предложений нет: данные в норме." in text
    assert "Повторы: нет" in text and "Стопы: нет" in text and "Зависания: нет" in text
    assert "Брифы не получились: нет" in text and "медиана — нет" in text


def test_body_rows_and_suggestions():
    st = stats(runs=2, stops=1, stuck=1, repeats=["c-aaaa"], failed_briefs=["c-bbbb"], tokens=4_200_000,
               run_rows=[RunRow("r-1", "c-aaaa", "A", 2, 418_000, 5, 0, "stop", "no access")],
               costly=[Costly("r-1 step 2", "c-aaaa", "A", 418_000, 5, "stop")],
               open_over_day=[OpenDecision("d-1", "Which format?", "2026-10-19T10:00:00", 60)],
               asked=3, answered=2, median_answer_hours=5)
    text = render.body(st, [Suggestion(1, "stuck", "period", "Some text", "applied")])
    assert "1. [applied] Some text" in text
    assert "\nRuns 2 · steps 0 · stops 1 · accepted 0 · tokens 4.2 M · 0 min · commits 0\n" in text
    assert "Stops: r-1 (c-aaaa, step 2): no access" in text and "Stuck runs: 1" in text
    assert "Repeats: c-aaaa" in text and "Failed briefs: c-bbbb" in text
    assert "| r-1 step 2 | c-aaaa | 418 K | 5 | stop |" in text
    assert "Asked 3, answered 2, median wait for an answer 5 h." in text
    assert '- d-1 "Which format?" — 60 h (created 2026-10-19T10:00:00)' in text
    assert not CYRILLIC.search(text)


def test_body_rows_in_russian():
    i18n.use("ru")
    st = stats(runs=2, stops=1, stuck=1, tokens=4_200_000,
               run_rows=[RunRow("r-1", "c-aaaa", "A", 2, 418_000, 5, 0, "stop", "нет доступа")],
               open_over_day=[OpenDecision("d-1", "Вопрос?", "2026-10-19T10:00:00", 60)],
               asked=3, answered=2, median_answer_hours=5)
    text = render.body(st, [Suggestion(1, "stuck", "period", "Текст", "applied")])
    assert "\nРанов 2 · шагов 0 · стопов 1 · принято 0 · токенов 4,2 M · 0 мин · коммитов 0\n" in text
    assert "Стопы: r-1 (c-aaaa, шаг 2): нет доступа" in text and "Зависания: 1" in text
    assert "Задано 3, отвечено 2, медиана ожидания ответа 5 ч." in text
    assert "- d-1 «Вопрос?» — 60 ч (создано 2026-10-19T10:00:00)" in text


@pytest.mark.parametrize("lang, heads", [
    ("en", ["Card", "Title", "Briefs", "Runs", "Stops", "Acceptances", "Tokens", "Status"]),
    ("ru", ["Карточка", "Заголовок", "Брифов", "Ранов", "Стопов", "Приёмок", "Токены", "Статус"])])
def test_table_heads_follow_the_language(lang, heads):
    from the_nod.review.collect import CardStat
    i18n.use(lang)
    text = render.body(stats(cards=[CardStat("c-a", "A", 1, 2, 0, 1, 5000, 3, "done")]), [])
    assert f"| {' | '.join(heads)} |" in text
    assert "| c-a | A | 1 | 2 | 0 | 1 | 5 K | done |" in text


def test_summary_lines():
    st = stats(runs=1, steps_done=1, tokens=3_800_000, minutes=12, commits=2)
    review = render.to_review(st, [], week="2026-43", now="2026-10-21T22:00:00")
    assert review.body == render.body(st, []) and review.generated_at == "2026-10-21T22:00:00"
    lines = render.summary(review, "reviews/2026-43.md").splitlines()
    assert lines[0] == ("Weekly review 2026-43 (14 Oct — 21 Oct): runs 1 · steps 1 · stops 0 · accepted 0"
                        " · tokens 3.8 M · 12 min · commits 2")
    assert lines[1:] == ["What to improve:", "  none", "wrote reviews/2026-43.md"]


def test_summary_lines_in_russian():
    i18n.use("ru")
    st = stats(runs=1, steps_done=1, tokens=3_800_000, minutes=12, commits=2)
    review = render.to_review(st, [], week="2026-43", now="2026-10-21T22:00:00")
    lines = render.summary(review, "reviews/2026-43.md").splitlines()
    assert lines[0] == ("Обзор недели 2026-43 (14 окт — 21 окт): ранов 1 · шагов 1 · стопов 0 · принято 0"
                        " · токенов 3,8 M · 12 мин · коммитов 2")
    assert lines[1:] == ["Что улучшить:", "  нет", "записано reviews/2026-43.md"]


def test_mark_body_swaps_one_status_only():
    text = render.body(stats(), [Suggestion(1, "stuck", "period", "One"), Suggestion(2, "stops", "c-a", "Two")])
    marked = render.mark_body(text, 2, "applied")
    assert "1. [proposed] One" in marked and "2. [applied] Two" in marked
    assert render.mark_body(marked, 2, "proposed") == text


@pytest.mark.parametrize("written, reader", [("en", "ru"), ("ru", "en")])
def test_mark_body_finds_the_heading_of_another_language(written, reader):
    """A review is marked in whatever language is in use now, not the one it was written in."""
    i18n.use(written)
    text = render.body(stats(), [Suggestion(1, "stuck", "period", "One")])
    i18n.use(reader)
    assert "1. [applied] One" in render.mark_body(text, 1, "applied")
