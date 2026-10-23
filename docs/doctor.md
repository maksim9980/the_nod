# Doctor and install

What a project needs from a machine is written in the `[needs]` table of `.nod/harness.toml` ([the manifest](manifest.md#needs)). `nod doctor` compares the machine with it, and `nod install` sets up what is missing. In Claude Code the same commands are `/nod doctor` and `/nod install`. Neither of them pulls, so both work offline.

## nod doctor

`nod doctor` prints a table `need | have | fix` and writes nothing. Exit code 0 means everything is in place, 1 means something is missing. `--json` prints `ok` and the list of checks, each with `name`, `ok`, `detail`, `fix` and `auto`.

The rows come in this order:

| Row | What it checks | Fix |
|---|---|---|
| `python ≥ X.Y` | on Windows, runs `python` from PATH and reads its version; the Microsoft Store stub counts as missing, since the MCP server of the plugin and the agents run `python`. On macOS and Linux, tries `python3`, then `python`, takes the first one that reaches the version and names it in the detail, for example `3.13 (python3)` | install Python from python.org and put `python` on PATH; on macOS and Linux `python3` on PATH is enough for this row |
| `nod` | the command from `needs.nod`; the row exists only when that key is not empty | `pip install -e <plugin folder>`, or install the package `the-nod` |
| `claude` | the command from `needs.claude` on PATH | install Claude Code |
| `nod plugin` | the plugin registry of Claude Code and the paths in `CLAUDE_CODE_PLUGIN_DIRS` | see below |
| `MCP server` | macOS and Linux only: runs `python` from PATH and reads its version, because the plugin starts its MCP server with the command `python` and stock Ubuntu and macOS have only `python3`. On Windows the `python` row is the same check, so this row does not exist there | Debian and Ubuntu: `sudo apt install python-is-python3`. macOS: link `python` to `python3` in a folder on PATH, `ln -s "$(command -v python3)" <folder in PATH>/python` |
| `driver job` | the login job of this repository ([the driver](driver.md#starting-at-login)), and that it runs this copy of the core. A job that points to another copy shows `points to <path>` | `nod driver install` |
| `<kind>/<name>` | a copy from `needs.skills`, `needs.agents` or `needs.rules` in the Claude folder has the same content as the file or folder in the repository | `nod install` |

The Claude folder is `CLAUDE_CONFIG_DIR` when that variable is set and not empty, otherwise `~/.claude`. Doctor reads the plugin registry and `settings.json` from it, and install puts the copies there.

The `nod plugin` row tells five cases apart:

| Case | Detail | Fix |
|---|---|---|
| the plugin is installed | `<version> from <marketplace>` | — |
| the plugin loads through `CLAUDE_CODE_PLUGIN_DIRS` | `via CLAUDE_CODE_PLUGIN_DIRS` | — |
| installed, and also in `CLAUDE_CODE_PLUGIN_DIRS` | `installed and also in CLAUDE_CODE_PLUGIN_DIRS (…) — double load` | remove the path from `env` in `~/.claude/settings.json` |
| installed from two marketplaces | `installed twice: a, b — double load` | `claude plugin uninstall nod@<marketplace>` |
| not installed | `not installed` | `claude plugin marketplace add <plugin folder>; claude plugin install nod@nod` |

`CLAUDE_CODE_PLUGIN_DIRS` is read from `env` in `settings.json` and from the environment of the process. A path counts as this plugin when it, its parent or its grandparent holds `.claude-plugin/plugin.json` with the name `nod`. The table shows the detail only for a failed check; `--json` has it for all of them.

A double load runs two copies of the pane in one window. They share the pane, and a button may answer in the copy that did not draw it.

## nod install

`nod install` takes the failed checks of `doctor` and works through them in this order:

1. The copies into the Claude folder. A file that differs is overwritten, but nothing in the Claude folder is deleted. Extra files in a target folder are named: `extra files in …, remove them by hand`.
2. The driver login job, like `nod driver install`.
3. A line `by hand: …` for each check that has no automatic fix: Python, `nod`, `claude`, the plugin, the `python` command of the MCP server (macOS and Linux), a copy whose source is missing from the repository.

`install` installs no packages and does not change the settings of Claude Code. After its steps it prints the `doctor` table. With nothing missing it prints `nothing to do`, and a second run changes nothing.

`--dry-run` prints `would do: …` and writes nothing; its exit code is 1 only when the plan has `by hand` lines. Without it the exit code is 0 when every check passes after the steps, 1 when one still fails (a `by hand` line, for example), and 2 when setting up the login job failed.

## A new machine

1. Install the plugin and restart Claude Desktop ([Install](../README.md#install)).
2. Clone the project and open a session in it. The state comes with the clone; type `/nod init` only if the project has no `.nod/` yet.
3. Type `/nod doctor`, then `/nod install`.
4. Close the `by hand` lines yourself, and run `/nod doctor` again until every row says `yes`.
