# The manifest

`.nod/harness.toml` tells the driver which commands write a brief, run a step and accept a card, whether the state syncs with a remote, and what the project needs from a machine. `nod init` writes it with every key, most of them with a comment, in the current language. It is committed with the rest of the state, and only the owner edits it: the driver restores the manifest if an agent changes it ([SECURITY.md](../SECURITY.md#checks-around-the-agent-command)).

An unknown key, a value of the wrong type or an unknown placeholder is an error that names the key, and the command that read the manifest exits with code 2.

```toml
lang = "en"
adapter = "default"
driver_host = ""

[commands]
brief = ""
run = ""
accept = ""

[git]
push = false

# [needs]
# python = "3.13"
# nod = ""
# claude = "claude"
# jobs = ["driver"]
# skills = []
# agents = []
# rules = []
```

## lang

`en` (the default) or `ru`. The environment variable `NOD_LANG` wins over it. The language applies to the CLI messages, the driver log, the agent prompts, the decisions the driver asks, the answers file for the agent, the descriptions of the MCP tools and the pane.

Text that Nod writes into the state stays in the language of the moment it was written: the questions of the decisions the driver asks and the progress lines of a run. Changing `lang` later does not rewrite it. When two machines work on one project with different languages, the state holds texts in both. The title line of `order.md` is English in every language, so the machines do not rewrite it back and forth.

Identifiers never follow the language: answers such as `done`, `postpone`, `accept`, results such as `solved`, statuses, commit subjects, JSON keys and file names are English.

## adapter

The set of default commands and prompts. Only `default` exists. Its prompts are in `the_nod/prompts/default/en/` and `the_nod/prompts/default/ru/`, and its briefs go to `docs/briefs/`.

## driver_host

The name of the machine that runs the driver, as the machine reports it (`hostname`). Empty means any machine. `nod driver once` and `nod driver` exit with code 2 on a machine other than `driver_host`, with the message `the driver of this project runs on <host>`.

## git

`[git] push` is `false` by default. Then Nod never talks to a remote: no pull before a write, no push after it, no fetch for the manifest check, and the driver lock is a local commit.

With `push = true`, every write runs `git pull --ff-only` first and pushes the current branch after the commit. This is what two machines need ([the driver](driver.md#the-lock-and-two-machines)). The agent's own `nod` calls push too, so the agent's code commits reach the remote even though the agent cannot run `git push`.

A manifest that exists but does not parse counts as `push = false`, with a warning on stderr, so a broken file never makes Nod talk to a remote by mistake.

## commands

`brief`, `run` and `accept` are shell lines. An empty line means the default command of the adapter:

```
claude -p --model sonnet --output-format json --permission-mode acceptEdits --permission-prompts none --allowedTools "…" --disallowedTools "…" --max-budget-usd 5
```

The cap is 5 USD for `brief`, 30 for `run` and 10 for `accept`. The allowed and denied tools of each command are listed in [SECURITY.md](../SECURITY.md#rights-of-the-agent). Its section [Limiting the agent further](../SECURITY.md#limiting-the-agent-further) shows how to print the default line and paste it here as a start.

Your own line replaces the default one completely, `--disallowedTools` included. Keep `--output-format json` in it: the driver reads the spend, the cost and a failed login from that output, and without it the spend counts as zero.

Nothing in Nod depends on the `sonnet` model: a different model or a lower cap goes into your own line.

The default `accept` line lets the agent run `python -m pytest` or `python3 -m pytest`, `nod` and the read-only git forms, but not the project's own command. When section 9 of the brief asks to run the program, the acceptance falls back to the tests. To check the program itself, write your own `accept` line that allows its command.

### Placeholders

A command may hold these placeholders. Their values are filled in before the line goes to the shell:

| Placeholder | Value |
|---|---|
| `{card}` | the card id, such as `c-4vmp` |
| `{brief}` | the brief path from the repository root; empty before the first brief |
| `{root}` | the absolute path of the repository root |
| `{answers}` | the file with the owner's answers for this card |
| `{result}` | the file the command must write its result to |
| `{prompt}` | the file that holds the prompt |
| `{step}` | the step number of a run |
| `{run}` | the run id |

`{title}` and `{step_title}` are free text from the card, so they exist in prompts only. In a command they are an error. A value with a quote, `;`, `&`, `|`, `` ` ``, `$`, `<`, `>`, `^` or a control character stops the command before it starts. Paths with spaces or non-Latin letters are fine.

The command runs at the repository root. The prompt goes to its stdin and is also saved in the `{prompt}` file. The environment holds every placeholder as `NOD_<NAME>` (`NOD_CARD`, `NOD_TITLE`, `NOD_RESULT` and so on) and `NOD_AGENT=1`, which keeps the agent from answering for the owner. The driver also puts a `nod` wrapper first on `PATH` and turns git hooks off with `GIT_CONFIG_PARAMETERS`. If your project needs its hooks on the agent's commits, remove that variable inside your own command.

### The result file

As its last action the command writes TOML to `{result}`, which is `.nod/driver/<card>.<brief|run|accept>.toml`.

Brief (`note` is optional):

```toml
brief = "docs/briefs/2026-10-22-export-habits-to-csv.md"
```

The path is from the repository root, uses only `A-Z a-z 0-9 . _ / -`, and the file must exist inside the repository.

Run (`result` is required, the rest is optional):

```toml
result = "ok"          # or "stop"
contracts_total = 3
contracts_done = 3
note = "the export button and the CSV writer are in"
```

Acceptance (`level` and `result` are required):

```toml
level = 2              # 1, 2 or 3: how deep the check went
result = "solved"      # "solved", "unsolved" or "unverified"
evidence = "the file opens in a spreadsheet: 3 habits, 30 days"
frames = [{ path = "docs/briefs/export-csv.png", caption = "the export dialog" }]
steps = ["Open Settings", "Press Export"]
report = "docs/briefs/export-csv-report.md"
```

When the work needs the owner's hands, one line replaces all of that. The driver turns it into an `owner-action` decision:

```toml
blocked = "add the email API key to .env"
```

A brief that is committed but has no result file is still picked up: see [the driver](driver.md#a-brief-without-a-result).

### The brief

The driver reads the brief from its file and ignores the chat answer of the agent. The file needs:

- a title line `# …` and a line `Date: YYYY-MM-DD. Status: …`;
- ten sections `## 1.` to `## 10.`, found by number, so their titles may be in any language;
- in section 4, one line per question to the owner: `N. Question: <wording>? Proposed: <answer>. Why: <reason>. Options: <option> | <option>.` `Proposed:` is required, and the proposed answer becomes the first option;
- in section 9, the check the acceptance follows;
- in section 10, the steps as lines `N. <step title>`. A brief without steps counts as a failed brief.

The labels `Date:`, `Status:`, `Question:`, `Proposed:`, `Why:`, `Options:` and `Outside the run:` may also come in Russian, as the Russian prompt writes them, and one brief may mix both. The full template is in the brief prompt, `the_nod/prompts/default/en/brief.md`.

## needs

What the project needs from a machine. `nod doctor` compares the machine with it, and `nod install` sets up what is missing ([doctor and install](doctor.md)). Without the table, or without a key, the defaults above apply.

| Key | Meaning |
|---|---|
| `python` | the lowest Python version, such as `3.13` |
| `nod` | the `nod` command. Empty means no check: the core comes with the plugin. Otherwise the first word is looked up on PATH; for `python`, `py` or `python3` doctor checks that Python finds the module `the_nod` |
| `claude` | the Claude Code command; empty means no check |
| `jobs` | jobs to set up; `driver`, the driver start at login, is the only one |
| `skills`, `agents`, `rules` | paths inside the repository, relative and without `..`. Each is copied to `<Claude folder>/<kind>/<file or folder name>` |
