"""English messages of the weekly review: the file body, the summary line, the suggestions and the errors.

Literal braces are doubled: every message goes through `str.format`.
Words that take a plural form come in three messages (`_one`, `_few`, `_many`): the language decides which
one a number takes (`the_nod.review.plural`). English needs two forms; the third repeats the second.
"""

MESSAGES = {
    # words
    "review.none": "none",
    "review.months": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec",
    "review.decimal": ".",
    "review.running": "running",
    "review.attempt_one": "attempt",
    "review.attempt_few": "attempts",
    "review.attempt_many": "attempts",
    "review.stop_one": "stop",
    "review.stop_few": "stops",
    "review.stop_many": "stops",
    "review.time_one": "time",
    "review.time_few": "times",
    "review.time_many": "times",

    # the file body and the summary
    "review.title": "# Weekly review {week} ({period})",
    "review.totals": "runs {runs} · steps {steps} · stops {stops} · accepted {accepted} · tokens {tokens}"
                     " · {minutes} min · commits {commits}",
    "review.h_improve": "## What to improve",
    "review.h_cards": "## By card",
    "review.h_kinds": "## By agent command",
    "review.h_costly": "## Most expensive",
    "review.h_failures": "## Least successful",
    "review.h_answers": "## Owner answers",
    "review.no_suggestions": "No suggestions: the data looks normal.",
    "review.cols_cards": "Card|Title|Briefs|Runs|Stops|Acceptances|Tokens|Status",
    "review.cols_kinds": "Command|Calls|Tokens|Median|Largest|Minutes",
    "review.cols_costly": "What|Card|Tokens|Minutes|Outcome",
    "review.line_repeats": "Repeats: {value}",
    "review.line_stops": "Stops: {value}",
    "review.line_stuck": "Stuck runs: {value}",
    "review.line_failed_briefs": "Failed briefs: {value}",
    "review.stop_entry": "{id} ({card}, step {step})",
    "review.repeat_entry": "{card} step {step} — {count} {times}",
    "review.run_label": "{id} step {step}",
    "review.answers": "Asked {asked}, answered {answered}, {tail}",
    "review.answers_median": "median wait for an answer {hours} h.",
    "review.answers_no_median": "median: none.",
    "review.open_decision": '- {id} "{question}" — {hours} h (created {created})',
    "review.summary_title": "Weekly review {week} ({period}): {totals}",
    "review.summary_improve": "What to improve:",
    "review.summary_written": "wrote {path}",

    # suggestions
    "review.s_brief_attempts": 'Card {card} "{title}": {count} brief {attempts}. Check the card text and the'
                               " adapter's brief prompt: questions for the owner should come as forks, not repeats.",
    "review.s_expensive_run": "Run {id} ({card}, step {step}): {tokens} against a median of {median}."
                              " Split the step into smaller contracts or narrow allowedTools in harness.toml.",
    "review.s_open_decision": 'Decision {id} "{question}" has waited {hours} h.'
                              " Answer or close it: the driver does not touch a card with an open decision.",
    "review.s_stops": "Card {card}: {count} {stops} in the period."
                      " Read the run notes and return the card to the backlog or rewrite the brief.",
    "review.s_stuck": "Stuck runs: {count}."
                      " Check that the run prompt requires `nod run progress` after each contract.",
    "review.s_tool_errors": "Run {id}: {count} tool errors."
                            " Look at .nod/driver/{card}.run.err.txt and allowedTools in harness.toml.",
    "review.s_unverified": "Unverified acceptances: {count}."
                           " The brief needs a check scenario the agent can run without the owner.",

    # errors and the output of `nod review`
    "review.bad_period": 'period: unreadable bounds "{since}" — "{until}"',
    "review.bad_since": "invalid --since date: {value}",
    "review.since_not_before": "--since {value} is not before the current time {now}",
    "review.no_review": 'no review "{week}"',
    "review.no_suggestion": "review {week} has no suggestion {n}",
    "review.marked": "marked {n}: {status}",
}
