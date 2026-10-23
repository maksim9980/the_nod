# The state format

The state of a project is the folder `.nod/` at the root of the main worktree. One object is one Markdown file: a TOML header between two `+++` lines, then a body for people.

```
+++
id = "c-4vmp"
title = "Export habits to CSV"
status = "ready"
created = "2026-10-21T09:12:40"
source = "owner"
brief = "docs/briefs/2026-10-21-export-habits-to-csv.md"
steps = [{ n = 1, title = "Add the CSV writer", done = true }, { n = 2, title = "Add the export button", done = false }]
+++
People want their habit data in a spreadsheet.
```

You may edit the files by hand. Commit the edit: the driver does not start while `.nod/` has uncommitted changes. A file that does not parse makes the commands that read it fail with exit code 2, and the error names the file and the line.

## Files

| File or folder | What it holds |
|---|---|
| `cards/<id>-<slug>.md` | a card: `id`, `title`, `status`, `created`, `source` (`owner`, `agent` or `import`), `brief`, `steps` (`n`, `title`, `done`), `closed_at`, `closed_by`. The body is the card text |
| `order.md` | the backlog order: a title line, then one line `<id>  <title>` per card. Only the first word of a line counts. Open cards missing from the file come after the listed ones |
| `decisions/<id>-<slug>.md` | a decision: `id`, `kind`, `created`, `question`, `proposed`, `options`, `reason`, `card`, and after the answer `answer`, `answered_at`, `answered_by` (the machine) and `note` |
| `runs/<id>.md` | a run of a card step: `id`, `card`, `started`, `step`, `finished`, `contracts_total`, `contracts_done`, `tokens`, `minutes`, `agents`, `tool_errors`, `result` (`ok` or `stop`). The body has one line per `nod run progress` and the closing note |
| `acceptance/<card>/index.md` | an acceptance: `card`, `level`, `result`, `created`, `evidence`, `frames` (`path`, `caption`), `steps`, `report`. The frames are copied next to it as `frame-<n>.<ext>` |
| `usage/<time>-<kind>-<card>.md` | the spend of one brief or acceptance command: `kind`, `card`, `at`, `tokens`, `minutes`, `agents`, `tool_errors`, `cost_usd`. A run keeps its spend in its run file |
| `reviews/<yyyy-ww>.md` | a weekly review ([the weekly review](review.md)) |
| `harness.toml` | the manifest ([the manifest](manifest.md)) |
| `driver.lock` | the driver lock: `host` and `at` ([the driver](driver.md#the-lock-and-two-machines)) |
| `state.json` | the snapshot for clients; local, see below |
| `seen.toml` | when you last looked at the state, `<machine> = "<time>"`, and `stale_since` while the state is stale; local |
| `driver.log`, `driver.log.1`, `driver/` | the driver log and its working files; local ([the driver](driver.md#local-files)) |

The local files are never committed, each machine has its own, and `nod init` lists them in `.gitignore`. Everything else is committed by the command that writes it.

## Ids, names and times

An id is a letter, a dash and four characters from `0-9` and `a-z`: `c-` for cards, `d-` for decisions, `r-` for runs. The file name of a card or a decision adds a slug of its title or question, up to 40 characters of letters in any script, digits and dashes. When the title changes, the file is renamed. Two files with the same id are an error.

Times are local time without a zone, `YYYY-MM-DDTHH:MM:SS`.

## Values

The values that Nod compares are English identifiers in every language, defined in `the_nod/vocab.py`:

| Field | Values |
|---|---|
| card `status` | `backlog`, `briefing`, `waiting-owner`, `ready`, `running`, `accepting`, `waiting-verdict`, `done`, `returned` |
| decision `kind` | `fork`, `verdict`, `owner-action`, `return`, `run-stuck`, `next-batch`, `pain`, `brief-yes` |
| answers | `done`, `postpone` (owner action); `yes`, `no` (next batch); `wait` (what hurts); `accept`, `return` (verdict); `rerun`, `backlog` (return); `restart`, `backlog` (hung run). A fork answer is free text |
| acceptance `result` | `solved`, `unsolved`, `unverified` |
| review suggestion `status` | `proposed`, `applied` |

The body of a decision may hold two marker lines that the driver writes: `Consumed: <time>` once it has applied the answer, and `Card: <id>` once a "What hurts?" answer became a card. A decision with such a line is not applied again.

Free text keeps the language it was written in, such as the question of a decision or the progress lines of a run ([lang](manifest.md#lang)).

## state.json

`state.json` is a cache built from the other files. Every write and every `nod status` rebuilds it, and you may delete it at any time. The pane reads it. `nod status --json` prints the same object.

| Key | What it holds |
|---|---|
| `schema` | `1`, the version of this contract |
| `generated_at`, `host`, `lang` | when, on which machine and in which language it was built |
| `fresh`, `stale_since` | whether writes are allowed, and since when they are not |
| `waiting` | the open decisions, oldest first: `id`, `kind`, `card`, `card_title`, `question`, `proposed`, `options`, `reason`, `created`; a `verdict` also has `acceptance` |
| `running` | the `running` cards: `card`, `card_title`, `step`, `step_title`, `run`, `started`, `contracts_done`, `contracts_total` |
| `since` | what changed since your last look on this machine, or in the last seven days: `from`, `runs`, `steps_done`, `accepted`, `tokens`, `cards_done` |
| `backlog` | `total`, and the first 15 cards in order (`top`): `id`, `title`, `status`, `brief`, `steps_total`, `steps_done`. Closed and returned cards are not counted |
| `lock` | the driver lock, or `null` |
| `review` | the latest weekly review: `week`, `since`, `until`, `runs`, `steps_done`, `stops`, `accepted`, `tokens`, `minutes`, `suggestions` (`n`, `text`, `status`) and `path`; `null` without one |
