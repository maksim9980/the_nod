# Commands

`nod` is a small command-line tool over the files in `.nod/`. Every command that changes the state goes through one write path: change the files, rebuild `.nod/state.json`, commit.

## Running nod

- With the package installed (`pipx install the-nod`, or `pip install -e .` in a clone) the command is `nod`.
- With the plugin only, the core is a file in the plugin folder: `python -P <plugin folder>/the_nod/__main__.py`. The second line of the `/nod` answer in Claude Code prints this command for your machine.
- In a clone of this repository, `python -m the_nod` works too.

The driver's agents always have `nod`: before each agent command the driver writes a `nod` wrapper into `.nod/driver/bin/` and puts that folder first on the agent's PATH.

## Where the state is

`--root` takes the repository root or the path to `.nod` itself. Without it, `nod` uses `.nod/` in the main worktree of the repository that holds the current folder, also when the command runs inside a worktree of that repository. Outside a git repository, `nod` looks for `.nod/` from the current folder upwards. A `--root` that points into a linked worktree is refused: the state is committed from the main worktree, and a write to the copy in the worktree would be lost.

`--json` gives JSON output. It goes before or after the subcommand.

## Writes and git

Each write commits `.nod/` with the subject `state: <what was done>`. Only `.nod/` goes into that commit, and the local files `state.json`, `seen.toml`, `driver.log`, `driver.log.1` and `driver/` never do, with or without `.gitignore`.

With `[git] push = true` in the manifest, a command first runs `git pull --ff-only` and pushes the branch after the write. If the push fails, the write stays in the local commit and the reason is printed to stderr. Without `push`, Nod runs no pull, push or fetch. See [the manifest](manifest.md#git).

Nod does not write its state on `main` or `master`, and not on a detached HEAD.

## First run in a repository

- Run `nod init` once per repository (in Claude Code, `/nod init`). After that the state travels with the repository.
- On `main` or `master` `init` refuses with exit code 3 and the hint `git switch -c <name>`. On a new branch with no commits it works, and its commit becomes the first one.
- `init` writes the manifest `.nod/harness.toml` in the current language, with every key and comments on most of them. It appends the local files to `.gitignore` (`.nod/state.json`, `.nod/seen.toml`, `.nod/driver.log`, `.nod/driver.log.1`, `.nod/driver/`), but does not commit `.gitignore`: commit that yourself.
- Git needs `user.name` and `user.email`, or the first state commit fails.

## Commands

| Command | What it does |
|---|---|
| `nod init` | creates `.nod/` at the root of the main worktree and commits it |
| `nod status [--since ISO] [--no-sync] [--peek]` | prints what waits for you, what runs, what changed, and the backlog. The text output marks the visit in `seen.toml`; `--peek` and `--json` do not. `--no-sync` skips the pull |
| `nod card add <title> [--body TEXT] [--source owner\|agent\|import] [--top]` | adds a card at the bottom of the backlog, or at the top with `--top` |
| `nod card move <id> --top\|--bottom\|--before ID\|--after ID` | moves a card in the backlog |
| `nod card close <id> [--by owner\|agent]` | closes a card |
| `nod card return <id> --note TEXT` | takes a card out of the queue and opens a `return` decision |
| `nod card show <id>` | prints a card: status, brief, steps, text |
| `nod decision list [--all]` | decisions without an answer; with `--all`, the answered ones too |
| `nod decision ask --kind KIND --question TEXT --proposed ANSWER [--option ANSWER]... [--reason TEXT] [--card ID]` | asks the owner; prints the decision id |
| `nod decision answer <id> <answer> [--note TEXT] [--free]` | answers a decision; the answer must be one of the options unless `--free` is given |
| `nod run start <card> [--step N] [--contracts N]` | starts a run of a card step; prints the run id |
| `nod run progress <id> --contracts-done N` | records the progress of a run; this is how the driver knows the run is alive |
| `nod run finish <id> --result ok\|stop [--contracts-done N] [--tokens N] [--minutes N] [--agents N] [--tool-errors N] [--note TEXT]` | finishes a run and records its spend |
| `nod accept <card> --level 1\|2\|3 --result solved\|unsolved\|unverified [--evidence TEXT] [--frame PATH --caption TEXT]... [--step TEXT]... [--report PATH]` | records an acceptance and opens the `verdict` decision. Up to six frames (PNG, JPEG, GIF, WebP); a frame over 300 KB is not copied |
| `nod import markdown --from FILE [--dry-run]` | turns each `## ` heading of a Markdown file into a backlog card with the text under it. A title that is already a card is skipped. Imported cards wait for a `next-batch` answer |
| `nod render backlog\|archive [--write PATH]` | prints the backlog, or the closed cards, as Markdown. It does not change the state |
| `nod driver [--interval S] [--passes N]` | the driver loop, until Ctrl+C. See [the driver](driver.md) |
| `nod driver once` | one driver pass; prints `<what was done>: <detail>` |
| `nod driver install\|uninstall [--dry-run]` | sets up or removes the driver start at login |
| `nod review week [--since ISO]` | writes the weekly review. See [the weekly review](review.md) |
| `nod review mark <week> <n> --applied\|--proposed` | sets the status of a review suggestion |
| `nod doctor` | checks the machine against the `[needs]` table of the manifest; writes nothing. See [doctor and install](doctor.md) |
| `nod install [--dry-run]` | sets up what `nod doctor` finds missing |
| `nod mcp` | the MCP server over stdio. See [the MCP server](mcp.md) |
| `nod migrate [--dry-run]` | moves the state of the older version to `.nod/`; see below |

The decision kinds for `--kind` are `fork`, `verdict`, `owner-action`, `return`, `run-stuck`, `next-batch`, `pain` and `brief-yes`. [How it works](how-it-works.md#decisions) lists what each one means.

## JSON output

Write commands with `--json` print one object:

- `card add`, `decision ask`, `run start`: `{"id": "<new id>"}`;
- `card move`, `card close`, `card return`, `decision answer`, `run progress`, `run finish`, `accept`: `{"ok": true}`;
- `init`: `{"created": "<path to .nod>"}`;
- `review week`: the fields of the review and `path`; `review mark`: `week`, `n` and `status`;
- `import markdown`: `imported` and `skipped`, or `would_import` and `skipped` with `--dry-run`.

`status --json` prints the snapshot, the same object as `.nod/state.json` ([the state format](state-format.md#statejson)). `decision list --json` prints a list of decisions with all their fields, and `card show --json` prints the card fields and its `body`. `doctor --json` and `install --json` are described in [doctor and install](doctor.md). `driver`, `render` and `mcp` print text whatever the flag.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Done. If a push failed, the write is in a local commit and the reason is on stderr. |
| `1` | Only `nod doctor` and `nod install`: something on the machine is missing. |
| `2` | An error: wrong arguments, no such card or decision, a broken state file or manifest, a transition that is not allowed, a git or file error, a detached HEAD, a command refused to the driver's agent. |
| `3` | The write is refused: the branch is `main` or `master`, or the state is stale. |

A stale state happens only with `[git] push = true`: `git pull --ff-only` failed. Writes stay off until a pull succeeds; run `git pull` yourself and repeat the command. `nod status` says so in its first line, and its JSON has the fields `fresh` and `stale_since`. `nod driver once` also exits with 3 on a stale state.

## Language of the output

Messages and errors follow `NOD_LANG`, then `lang` of the manifest, then English. `--help` follows `NOD_LANG` only, because it is printed before the manifest is read. An unknown value of `NOD_LANG` is refused with exit code 2: `error: NOD_LANG=<value>: unknown language, use en or ru`. The identifiers stay English in both languages: answers such as `done` and `accept`, results such as `solved`, statuses, commit subjects and JSON keys.

## Migrating from `.sprintboot/`

The older version of Nod was called SprintBoot and kept its state in `.sprintboot/`. When `nod` or the pane finds that folder and no `.nod/`, it says `found .sprintboot/ from an older version: run nod migrate`. `nod migrate`, or `/nod migrate` in Claude Code, moves the folder to `.nod/` and commits the move as `state: migrate .sprintboot to .nod`. In the manifest it renames the `[needs]` key `sb` to `nod` and warns about lines that still call `sb` or `sprintboot`.

The migration also rewrites the Russian identifiers of the older version in the state files to the English ones, and sets an unknown adapter to `default`. It adds `lang = "ru"` and `[git] push = true` to the manifest when they are missing, because the older version spoke Russian and always synced with origin. It points the `.gitignore` lines at `.nod/`. With `push`, it pulls before the move and pushes after the commit.

It refuses on `main` or `master` (exit code 3) and on uncommitted changes, and a failure undoes the move. `--dry-run` shows the plan and changes nothing.

Run it on one machine right after `git pull`. Every other machine pulls the migration and then runs `nod migrate` once more: that moves its local files (`state.json`, `seen.toml`, `driver.log`, `driver/`) into `.nod/`.
