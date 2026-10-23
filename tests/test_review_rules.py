# tests/test_review_rules.py
import dataclasses
import re

import pytest

from the_nod import i18n
from the_nod.model import Suggestion
from the_nod.review import plural
from the_nod.review.collect import KindStat, OpenDecision, RunRow, Stats
from the_nod.review.rules import fmt_tokens, merge_status, suggest

CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def stats(**kw) -> Stats:
    base = dict(since="2026-10-14T00:00:00", until="2026-10-21T00:00:00", runs=0, steps_done=0, stops=0, stuck=0,
                repeats=[], accepted=0, unverified=0, tokens=0, minutes=0, commits=0, asked=0, answered=0,
                median_answer_hours=None, open_over_day=[], cards=[],
                kinds=[KindStat(k, 0, 0, 0, 0, 0) for k in ("brief", "run", "accept")],
                run_rows=[], spend_rows=[], costly=[], failed_briefs=[], brief_attempts={})
    return Stats(**{**base, **kw})


def every_rule_stats() -> Stats:
    return stats(brief_attempts={"c-aaaa": 3, "c-bbbb": 2},
                 run_rows=[RunRow("r-1", "c-aaaa", "A", 1, 10_000_000, 5, 6, "ok", ""),
                           RunRow("r-2", "c-aaaa", "A", 2, 1_000_000, 5, 0, "stop", ""),
                           RunRow("r-3", "c-aaaa", "A", 2, 1_000_000, 5, 0, "stop", "")],
                 open_over_day=[OpenDecision("d-1", "Which format?", "2026-10-10T00:00:00", 48)],
                 stuck=1, unverified=2)


RULE_IDS = [(1, "brief-attempts", "c-aaaa"), (2, "expensive-run", "r-1"), (3, "open-decision", "d-1"),
            (4, "stops", "c-aaaa"), (5, "stuck", "period"), (6, "tool-errors", "r-1"), (7, "unverified", "period")]


def test_each_rule_fires_once_per_target():
    got = suggest(every_rule_stats())
    assert [(s.n, s.rule, s.target) for s in got] == RULE_IDS
    assert got[1].text == ("Run r-1 (c-aaaa, step 1): 10.0 M against a median of 1.0 M. "
                           "Split the step into smaller contracts or narrow allowedTools in harness.toml.")
    assert got[0].text == ('Card c-aaaa "A": 3 brief attempts. Check the card text and the adapter\'s brief prompt: '
                           "questions for the owner should come as forks, not repeats.")
    assert got[2].text == ('Decision d-1 "Which format?" has waited 48 h. '
                           "Answer or close it: the driver does not touch a card with an open decision.")
    assert got[3].text == ("Card c-aaaa: 2 stops in the period. "
                           "Read the run notes and return the card to the backlog or rewrite the brief.")
    assert got[4].text == "Stuck runs: 1. Check that the run prompt requires `nod run progress` after each contract."
    assert got[5].text == ("Run r-1: 6 tool errors. "
                           "Look at .nod/driver/c-aaaa.run.err.txt and allowedTools in harness.toml.")
    assert got[6].text == ("Unverified acceptances: 2. "
                           "The brief needs a check scenario the agent can run without the owner.")
    assert all(s.status == "proposed" for s in got)
    assert not any(CYRILLIC.search(s.text) for s in got)


def test_each_rule_text_in_russian():
    i18n.use("ru")
    got = suggest(dataclasses.replace(every_rule_stats(), open_over_day=[
        OpenDecision("d-1", "Вопрос?", "2026-10-10T00:00:00", 48)]))
    assert [(s.n, s.rule, s.target) for s in got] == RULE_IDS
    assert got[1].text == ("Ран r-1 (c-aaaa, шаг 1): 10,0 M при медиане 1,0 M. "
                           "Разбей шаг на меньшие контракты или сузь allowedTools в harness.toml.")
    assert got[0].text == ("Карточка c-aaaa «A»: 3 попытки брифа. Проверь текст карточки и промпт брифа адаптера: "
                           "вопросы к владельцу должны идти развилками, а не повторами.")
    assert got[2].text == ("Решение d-1 «Вопрос?» ждёт 48 ч. "
                           "Ответь или закрой: драйвер не трогает карточку с открытым решением.")
    assert got[3].text == ("Карточка c-aaaa: 2 стопа за период. "
                           "Прочитай заметки ранов и верни карточку в бэклог или перепиши бриф.")
    assert got[4].text == "Зависаний 1. Проверь, что промпт рана требует `nod run progress` после каждого контракта."
    assert got[5].text == ("Ран r-1: 6 ошибок инструментов. "
                           "Посмотри .nod/driver/c-aaaa.run.err.txt и allowedTools в harness.toml.")
    assert got[6].text == "Приёмок «не проверено»: 2. В брифе нужен сценарий проверки без рук владельца."


def test_empty_stats_suggest_nothing():
    assert suggest(stats()) == []


def test_expensive_needs_two_runs_and_median_not_exceeded():
    assert suggest(stats(run_rows=[RunRow("r-1", "c-a", "A", 1, 9, 0, 0, "ok", "")])) == []
    assert suggest(stats(run_rows=[RunRow("r-1", "c-a", "A", 1, 3, 0, 0, "ok", ""),
                                   RunRow("r-2", "c-a", "A", 1, 5, 0, 0, "ok", "")])) == []


def test_merge_status_keeps_applied_by_rule_and_target():
    old = [Suggestion(1, "stuck", "period", "old text", "applied")]
    new = [Suggestion(1, "brief-attempts", "c-a", "x"), Suggestion(2, "stuck", "period", "new text")]
    merged = merge_status(new, old)
    assert [s.status for s in merged] == ["proposed", "applied"] and merged[1].text == "new text"
    assert [s.n for s in merged] == [1, 2] and new[1].status == "proposed"


def test_review_roundtrip_with_suggestions():
    from the_nod.model import Review
    r = Review(week="2026-W43", since="a", until="b", generated_at="c", runs=2,
               suggestions=[Suggestion(1, "stuck", "period", "t")])
    assert Review.from_meta(r.to_meta()) == r


def test_fmt_tokens():
    assert [fmt_tokens(n) for n in (0, 999, 1234, 418000, 1_250_000, 10_000_000, 1_000_000)] == [
        "0", "999", "1 K", "418 K", "1.2 M", "10.0 M", "1.0 M"]


def test_fmt_tokens_uses_the_decimal_comma_in_russian():
    i18n.use("ru")
    assert [fmt_tokens(n) for n in (999, 1234, 418000, 1_250_000, 10_000_000)] == [
        "999", "1 K", "418 K", "1,2 M", "10,0 M"]


def test_expensive_ignores_unfinished_run():
    rows = [RunRow("r-1", "c-a", "A", 1, 10_000_000, 0, 0, "ok", ""), RunRow("r-2", "c-a", "A", 2, 4_000_000, 0, 0, "ok", ""),
            RunRow("r-3", "c-a", "A", 3, 0, 0, 0, "", "")]
    assert suggest(stats(run_rows=rows)) == []


def test_expensive_median_zero_is_silent():
    rows = [RunRow(f"r-{i}", "c-a", "A", i, 0, 0, 0, "", "") for i in range(3)]
    rows.append(RunRow("r-9", "c-a", "A", 9, 5_000_000, 0, 0, "ok", ""))
    assert [s.rule for s in suggest(stats(run_rows=rows))] == []


def test_plural_forms_for_five():
    rows = [RunRow(f"r-{i}", "c-aaaa", "A", i, 0, 0, 0, "stop", "") for i in range(5)]
    got = suggest(stats(brief_attempts={"c-aaaa": 5}, run_rows=rows))
    assert "5 brief attempts" in got[0].text and "5 stops in the period" in got[1].text
    i18n.use("ru")
    got = suggest(stats(brief_attempts={"c-aaaa": 5}, run_rows=rows))
    assert "5 попыток брифа" in got[0].text and "5 стопов за период" in got[1].text


@pytest.mark.parametrize("lang, forms", [
    ("en", {1: "one", 2: "many", 5: "many", 11: "many", 21: "many", 22: "many"}),
    ("ru", {1: "one", 2: "few", 4: "few", 5: "many", 11: "many", 12: "many", 21: "one", 22: "few", 25: "many"})])
def test_plural_rule_per_language(lang, forms):
    i18n.use(lang)
    assert {n: plural.form(n) for n in forms} == forms


def test_every_language_has_a_plural_rule():
    assert set(plural.RULES) == set(i18n.LANGS)


def test_pick_takes_the_message_of_the_form():
    i18n.use("ru")
    assert [plural.pick(n, "review.attempt_one", "review.attempt_few", "review.attempt_many")
            for n in (21, 22, 25)] == ["попытка", "попытки", "попыток"]
    i18n.use("en")
    assert [plural.pick(n, "review.attempt_one", "review.attempt_few", "review.attempt_many")
            for n in (1, 3)] == ["attempt", "attempts"]
