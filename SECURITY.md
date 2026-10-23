# Security policy

## Supported versions

Only the 0.1.x line receives security fixes.

## Reporting a vulnerability

Report it privately as a GitHub Security Advisory: <https://github.com/maksim9980/the_nod/security/advisories/new>

Do not open a public issue or pull request for a vulnerability. Include the Nod version, your operating system, the steps to reproduce, and what an attacker gains. The advisory thread is where the fix and the disclosure date get agreed.

These count as security problems:

- the agent gets past a limit described below: it edits a denied path, runs a command outside the allowlist, or changes the git hooks, the git config, or the manifest without the driver noticing
- an agent running under `NOD_AGENT=1` answers a decision, closes or returns a card, accepts a card, finishes a run, or runs another command refused to it below
- Nod talks to a git remote while `[git] push` is off
- free text from a card title reaches a shell command

## What the driver does on your machine

`nod driver` watches the `.nod/` state of one repository. When a card needs work, it starts `claude -p` in that repository and passes the prompt on stdin. That process is an AI agent running as your user, with the rights listed here. Only the listed limits apply: Nod does not run the agent in a sandbox or a container.

### Rights of the agent

With the default commands (`brief`, `run`, and `accept`, defined in `the_nod/adapters/default.py`), the driver runs `claude -p --model sonnet --permission-mode acceptEdits --permission-prompts none`. File edits inside the working folder, the repository root, are accepted without a prompt, and no permission prompt is shown, so the allowlist decides what the agent may run.

| Allowed by `--allowedTools` | Brief | Run | Acceptance |
|---|---|---|---|
| Read-only git in fixed forms: `git status`, `git status --short`, `git log --oneline -20`, `git log -5`, `git diff`, `git diff --stat`, `git diff --cached` | yes | yes | yes |
| `git add *` and `git commit *` | yes | yes | no |
| `nod *`, `python -m the_nod *` and `python3 -m the_nod *` | yes | yes | yes |
| `python -m pytest`, `python -m pytest *`, `python3 -m pytest` and `python3 -m pytest *` | no | yes | yes |
| The `Agent` tool | yes | yes | yes |

The budget cap, `--max-budget-usd`, is 5 USD for a brief, 30 for a run, and 10 for an acceptance. It applies to each agent command separately.

`--disallowedTools` denies edits to `.git/`, to `.claude/`, to the state files under `.nod/` (`harness.toml`, `cards/`, `decisions/`, `runs/`, `acceptance/`, `order.md`, `driver.lock`), and to the `nod` wrapper in `.nod/driver/bin/`. It also denies git commands with `--ext-diff`, which runs an external program.

The allowlist is not a sandbox. The agent can edit test files, and `python -m pytest` (or `python3 -m pytest`) runs them with your user rights. Give the driver only projects whose tests you are willing to have the agent write and run.

### Git

- The agent commits to the current branch. The `git push` command is not allowed for it. Nod does not write its state on `main` or `master`.
- The state is local by default. Without `[git] push = true` in `.nod/harness.toml`, Nod runs no pull, push, or fetch.
- With `push = true`, Nod pulls (fast-forward only) before it writes state and pushes the current branch afterwards. The agent's own `nod` calls, such as `nod run progress` and `nod card add`, write state too. With `push = true` each of them pushes the branch, including the agent's code commits, even though the agent cannot run `git push` itself.
- Git hooks are off while the agent command runs: `core.hooksPath` points to an empty folder, `.git/nod-no-hooks`.

### Checks around the agent command

Before and after each agent command the driver compares the git hooks, the git config, uncommitted edits in `.nod/`, and the manifest `.nod/harness.toml`. These checks run whatever command the manifest sets.

Restored by the driver:

- files put into the empty hooks folder `.git/nod-no-hooks` are removed, because a file there would run as a hook
- uncommitted edits in `.nod/` are rolled back to the last commit, except in the local files listed below
- `.nod/harness.toml` is put back to its earlier version

Reported only, not undone:

- changes to files in `.git/hooks`
- changes to the git config

A finding opens an `owner-action` decision. For a restored item it says what was put back. For a reported item it asks you to check the change and remove it yourself.

One case opens no decision: uncommitted edits in `.nod/` that do not roll back, or a check of `.nod/` that fails with an error. Any write would then commit the agent's edits, so the driver writes nothing, not even the decision. The log gets an `ERROR` line, and the next pass refuses on the dirty tree (`lock-lost`) until you clean `.nod/` yourself.

Not checked: edits to `.nod/` that the agent commits, and the local files `state.json`, `seen.toml`, `driver.log`, `driver.log.1` and the `driver/` folder, where the agent writes its results. The agent writes its own records through `nod`, and git cannot tell those commits from other ones.

Under `NOD_AGENT=1` the agent cannot answer decisions, close or return cards, accept a card, finish a run, or reorder cards. It cannot start the driver, import cards, migrate the state, run `nod install` (which registers login jobs and copies files into `~/.claude`) or `nod init`, or write the backlog view to a file with `nod render --write`, which takes any path. Of the decision kinds it may ask only `owner-action`; the other kinds are the driver's own questions. Only you answer a decision.

The driver puts a `nod` wrapper in `.nod/driver/bin/` and places that folder first on the PATH of the agent command.

Global hooks and plugins from `~/.claude` also run inside the agent command, and their spend is not in Nod's spend lines: in the [field test](docs/field-test.md) a global security-review plugin started 4 extra sessions on another model, about 70,000 tokens. A command in your manifest with `--setting-sources project` turns them off.

### Autostart

`nod driver install` starts the driver at login: Task Scheduler on Windows, a LaunchAgent on macOS, and `systemd --user` or an `@reboot` crontab line on Linux. `nod driver uninstall` removes it. On Linux, installing and removing were checked live under WSL with Ubuntu 24.04: the `systemd --user` unit was started with `enable --now`, and the crontab line was written and removed. Starting at login or after a reboot was not tested. The macOS setup is covered by tests only.

## Limiting the agent further

- Write your own allowlist. A command in the `[commands]` table of `.nod/harness.toml` replaces the default line completely, including `--disallowedTools`. To start from the default, print it (Nod must be installed with pip, or you must run the command from a clone):
  ```
  python -c "from the_nod.adapters import default; print(default.COMMANDS['run'])"
  ```
  The line contains `"` characters, so paste it into the manifest as a TOML multi-line literal string, between `'''` marks, and then narrow `--allowedTools`:
  ```toml
  [commands]
  run = '''<the printed line>'''
  ```
- Add `--setting-sources project` to your commands to keep user-level hooks and plugins out of the agent.
- Lower `--max-budget-usd` in your commands.
- Set `driver_host = "laptop"` in the manifest, using the name your machine reports. The driver then refuses to run on any other machine.
- Skip autostart and start passes yourself with `nod driver once`.
- Point the driver at a separate clone of the repository, away from your own working tree.

## What Nod does not do

- It does not push unless you set `[git] push = true`.
- It does not answer decisions for you. The driver, the pane, and the agents leave every decision to the owner.
- It does not send data anywhere. The core has no network code and no telemetry. The only outside traffic comes from the `claude` command, under your own Claude Code login and settings, and from git when you turn on `push`.
