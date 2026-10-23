# The weekly review

`nod review week` collects the numbers of a period and writes them to `.nod/reviews/<yyyy-ww>.md`, with suggestions on what to change in the harness. The pane shows the latest review in its "Weekly review" zone.

## Running it

```
nod review week [--since 2026-10-15T00:00:00]
```

The period is `[--since, now)`, seven days by default. `--since` is a local time without a zone, and it must be earlier than now; otherwise the command refuses with exit code 2. The week is the ISO week of the end of the period, such as `2026-43`. The file is committed as `state: review week <week>`, and running the command again in the same week overwrites it.

## What it reads

Only the state:

- `runs/`: the runs finished in the period (or started, if not finished yet) with their steps, stops, tokens, minutes and tool errors;
- `acceptance/`: the acceptances of the period;
- `decisions/`: the decisions asked and answered in the period, the median wait for an answer, the decisions open for more than a day, and the hung runs (`run-stuck`);
- `usage/`: the spend of briefs and acceptances;
- `git log` of `.nod/`: the number of state commits, and the brief attempts, counted by the commits `state: driver brief <card> briefing`. Outside git, the attempts are counted from the `brief` records in `usage/`.

## The file

A TOML header with the numbers and the suggestions, then Markdown: a line of totals, "What to improve", "By card", "By agent command", "Most expensive", "Least successful" and "Owner answers".

## Suggestions

The suggestions are numbered from 1 in the order of the rules. Each one has a status, `proposed` (new) or `applied`.

| Rule | When it fires | What it suggests |
|---|---|---|
| `brief-attempts` | a card had more than 2 brief attempts | check the card text and the brief prompt of the adapter |
| `expensive-run` | a run cost more than twice the median of the period in tokens; the median counts runs with tokens, at least 2 of them | split the step into smaller pieces or narrow `allowedTools` |
| `open-decision` | a decision waited 24 hours or more | answer or close it: the driver does not touch a card with an open decision |
| `stops` | a card had 2 or more stops in the period | read the run notes, return the card or rewrite the brief |
| `stuck` | a run hung in the period | check that the run prompt asks for `nod run progress` |
| `tool-errors` | a run had 5 or more tool errors | read `.nod/driver/<card>.run.err.txt` and `allowedTools` |
| `unverified` | an acceptance came out `unverified` | add a check to the brief that the agent can run without the owner |

The thresholds are constants in `the_nod/review/rules.py`. When the review is written again, a suggestion keeps its status if the new review has one with the same rule and the same target.

## Marking a suggestion

```
nod review mark 2026-43 1 --applied
```

`--applied` sets suggestion 1 of week `2026-43` to `applied`, `--proposed` sets it back. The header and the line `N. [status]` of "What to improve" both change. A missing review or number is refused with exit code 2.

On the pane, "Apply the suggestions" puts a prompt into the pane footer, "Goes to the chat", and "Send" sends it to the chat. The prompt asks the agent to open the review, go through the `proposed` items, turn each into a change of the harness (the project's `harness.toml`, the adapter prompts or the project's `CLAUDE.md`), and mark each applied item with `nod review mark`.
