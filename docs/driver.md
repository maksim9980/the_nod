# The driver

`nod driver` is a process on the owner's machine. It moves cards forward whenever that needs no decision, and it never answers a decision itself. Every agent command it starts is a `claude -p` call from the [manifest](manifest.md#commands).

## Running it

- `nod driver once` makes one pass and prints one line.
- `nod driver` repeats passes until Ctrl+C. It writes each pass to `.nod/driver.log` as `pass: <what was done> — <detail>` and shows the log on the screen too. It prints the pass line after each pass, except a `foreign`, `stale` or `busy` line that repeats the one before.
- `nod driver install` starts the loop at login ([below](#starting-at-login)).

`--dry-run` works only with `install` and `uninstall`. A pass runs the agent, so `nod driver once --dry-run` and `nod driver --dry-run` are refused with exit code 2.

The loop makes a pass at once, then looks every 30 seconds (`--interval`). After a pass that did something, the next pass comes at the next look. After a quiet pass (`idle`, `foreign`, `stale`, `busy`, `error`), the next one waits until a file in `cards/`, `decisions/` or `runs/`, or `order.md`, or `harness.toml` changes, or five minutes pass. `--passes N` stops after N passes.

An agent under the driver cannot start a driver: `nod driver` refuses under `NOD_AGENT=1`.

## What a pass does

1. Opens the state. With `[git] push = true` this is a `git pull --ff-only`; if it fails, the pass ends as `stale`.
2. Checks `driver_host`: `nod driver once` and `nod driver` exit with code 2 on a machine other than `driver_host`.
3. Takes the local pid file `.nod/driver/pid`. If another driver on this machine holds it, the pass ends as `busy`.
4. Reads the lock `.nod/driver.lock`. If another machine took it less than an hour ago, the pass ends as `foreign`.
5. If `.nod/` has uncommitted changes, the pass ends as `lock-lost`, since any write would commit them.
6. Applies the answers you gave since the last pass, one by one, at most 20 per pass. An answer that starts a new brief ends the pass there.
7. Starts at most one action, the first that fits:
   1. a hung run: a `running` card without an open run, or with no record in its run file for 40 minutes, see [hangs](#hangs);
   2. the acceptance of an `accepting` card;
   3. if no run is open, a run of the next open step of the first `ready` card;
   4. a brief of the first `briefing` card, then of the first `backlog` card that you or an agent added;
   5. nothing (`idle`) while any card is still in the queue;
   6. the `next-batch` question when only imported cards are left in the backlog;
   7. the "What hurts?" question when the backlog is empty.

Cards go in the order of `order.md`. A card with an open decision is skipped by every action except the check for a hung run. A `next-batch` or "What hurts?" question is not asked again while one is open, or for a day after you answered `no` or `wait`.

## The pass line

A pass prints `<what was done>: <detail>`:

| First word | Meaning |
|---|---|
| `brief`, `run`, `accept`, `stuck` | the action of step 7 ran; the detail names the card, or says `failed, see driver.log` |
| `react` | an answer started a new brief |
| `next-batch`, `pain` | the driver asked that question; the detail is the decision id |
| `idle` | nothing to do |
| `foreign` | `work in progress on <machine> since <time>` |
| `stale` | `the state has been stale since <time>`; `nod driver once` exits with 3 |
| `busy` | `the driver is already running (pid N)` |
| `lock-lost` | the lock was not taken: `dirty tree: <files>`, or `push failed` |
| `error` | the pass stopped on an error; the detail and `driver.log` say which |

## Owner actions

The driver opens an `owner-action` decision when a command needs what only you can give:

- the command wrote `blocked = "<what to do>"` into its result file;
- `claude -p` reported a failed login. The question then is `Log in to claude: run claude /login in a terminal`, followed by what claude said;
- the checks around the command found something ([below](#checks-around-the-agent-command)).

The card keeps its status, and the open decision holds it. `done` lets the next pass repeat the step that waited. A run that stopped this way is finished as `stop`, and its step runs again. `postpone` moves the card to the bottom of the backlog.

Agents can open an `owner-action` themselves when they can go on without you. The driver does not touch such a decision when it has no card; only the agent that asked reads the answer. [Owner actions for your agents](agents.md) has the rules to put into your project.

## Checks around the agent command

Before and after each command the driver compares the git hooks, the git config, the uncommitted changes in `.nod/` and the manifest. It restores what it can and opens an `owner-action` that says what changed. The details, and what is not checked, are in [SECURITY.md](../SECURITY.md#checks-around-the-agent-command).

When uncommitted changes in `.nod/` do not roll back, or the check of `.nod/` fails with an error, the driver writes nothing at all, because any write would commit the agent's changes. The log gets an `ERROR` line, and the next pass ends as `lock-lost: dirty tree`. Clean `.nod/` yourself, then the driver goes on.

## A brief without a result

An agent may stop before it commits the brief and writes the result file, when its budget or its turns run out. The driver then looks for the brief itself. A candidate is a `docs/briefs/*.md` file, except `*.plan.md` and `*.verdict.md`, that `git status` shows as new or changed and that is not older than the start of the command. Of several, the newest wins. The driver parses it like any brief, commits it as `docs(brief): <file name>` and writes the result file for the agent.

Before it starts a brief command, the driver also checks the last attempt. First comes the result file `.nod/driver/<card>.brief.toml`; you may write it by hand, and the log says `adopted the result of the last attempt`. Then comes a candidate written inside the window of the last command, from the prompt file to the `.out.txt` file (`adopted the brief of the last attempt`). Without an `.out.txt` file, only a candidate whose `# …` title matches the card title counts. A repeated brief, one with your answers or notes, always goes through the command.

A brief fails when the command fails, the result is broken, or the brief has no steps. After the second failed attempt in a row the card is `returned` with a `return` decision. The attempts are counted in `.nod/driver/attempts.toml`.

## The lock and two machines

Two machines need a shared git remote and `[git] push = true`. Without `push`, each machine has its own state and nothing syncs.

The lock `.nod/driver.lock` holds the machine name (`host`) and the time (`at`), and it travels through git. A lock of another machine younger than an hour stops the pass as `foreign`. An older one counts as abandoned, and the driver takes it over. The lock is written in the same commit as the first change of the action. With `push = true` it counts as taken only if the push went through; if the push fails, the commit is undone and the command does not start. At worst a run starts later, never twice. While a command runs, the driver renews the lock every 20 minutes with a `state: driver heartbeat` commit.

The lock time is local time without a zone, so both machines must be in the same time zone. Texts that Nod writes into the state follow the language of the machine that writes them ([lang](manifest.md#lang)); set the same `lang` on both. Set `driver_host` to keep the driver on one machine.

## Hangs

A run counts as hung when the agent command has printed nothing and the run file has had no record for 40 minutes. The agent records progress with `nod run progress <run> --contracts-done N`, and the run prompt asks for it after each finished piece. The driver kills the whole process tree, finishes the run as `stop`, sets the card to `returned` and opens a `run-stuck` decision: `restart` makes the card `ready` again, `backlog` moves it to the bottom of the backlog. The driver never restarts a run by itself.

After a driver restart, a `running` card whose run has had no record for 40 minutes is handled the same way.

`claude -p --output-format json` prints nothing until the command ends, and a brief or an acceptance has no run file to write to. So a brief or an acceptance that takes longer than 40 minutes is stopped. A stopped brief counts as a failed attempt. A stopped acceptance is recorded as `unverified`, and the verdict still waits for you.

## Local files

These files never go into git, even without `.gitignore`:

- `.nod/driver/`: the files of the last command of each kind: the prompt (`<card>.<kind>.prompt.md`), the result (`<card>.<kind>.toml`), the last 64 KB of stdout and stderr (`<card>.<kind>.out.txt`, `.err.txt`). Also the owner's answers for the next brief (`<card>.answers.md`), the brief attempts (`attempts.toml`), the pid file (`pid`), the `nod` wrappers for the agents (`bin/`), and on macOS the output of the login job (`autostart.log`). Before each agent command the driver writes the wrappers again and removes everything else from `bin/`. On Windows `bin/` also holds `nod.cmd` for cmd and PowerShell; it is written in the OEM code page, so in a console switched to UTF-8 (`chcp 65001`) it fails when the path of Python or of the core has non-ASCII characters. When the OEM code page cannot encode that path, `nod.cmd` is written in UTF-8 instead and then works only under `chcp 65001`. The agents run the `sh` wrapper `nod` in Git Bash and are not affected.
- `.nod/driver.log`: one line per event, `<time> <LEVEL> <text>`. At 1 MB it moves to `driver.log.1`. After each command it has `output <kind> <card>: code …` and, when claude printed its JSON result, `claude result <kind> <card>: subtype …, is_error …, terminal_reason …, turns …, $ …`. That line tells why the agent stopped. After a brief or an acceptance a `spend` line follows with the tokens, minutes and cost; a run keeps its spend in its run file. These lines count the agent session only: your own Claude Code plugins and hooks run inside it, and their spend is not there (in the [field test](field-test.md) a global security-review plugin started 4 extra sessions on another model, about 70,000 tokens). `--setting-sources project` in your own commands keeps them out.
- `.nod/state.json` and `.nod/seen.toml`: the snapshot for the pane and the times you last looked, per machine.

## Starting at login

`nod driver install` sets up a job that starts `nod driver` for this repository at login. The job runs the core as a file, `<python> -P <core>/__main__.py --root <repository> driver`, so it needs neither pip nor `PYTHONPATH`. A path with spaces is quoted the way the job format needs. `nod driver uninstall` removes it. With `--dry-run` both print the files and commands and change nothing. `nod install` sets up the same job when `[needs] jobs` lists `driver`, which is the default.

| System | What is set up | When it starts |
|---|---|---|
| Windows | a Task Scheduler task `Nod driver <folder> <hash>`, run at logon with limited rights. It uses `pythonw.exe` when there is one, so no console window opens | at the next logon |
| macOS | a LaunchAgent `~/Library/LaunchAgents/the-nod.driver.<hash>.plist`, loaded with `launchctl bootstrap`. Its output goes to `.nod/driver/autostart.log` | now, and at every login |
| Linux | a `systemd --user` unit `nod-driver-<hash>.service` in `~/.config/systemd/user/` (or under `$XDG_CONFIG_HOME`), enabled with `systemctl --user enable --now`. Without `systemd --user`, a crontab line `@reboot … # nod-driver-<hash>` | now with systemd, at the next boot with cron |

`<hash>` is eight characters derived from the repository path, so two repositories with the same folder name get two jobs. On Windows the task command may not be longer than 261 characters. With a longer path `install` refuses with exit code 2 and asks to move the repository to a shorter path, or to install Nod with pip into a short path: the core of the plugin sits in Claude Code's own folder, which you do not choose.

On macOS and Linux the job gets the `PATH` of the shell that ran `nod driver install`, since launchd, systemd and cron start jobs with a short `PATH` where `claude` is often missing. After you change your `PATH`, run `nod driver install` again. With systemd, `enable --now` does not restart a driver that is already running: the new `PATH` applies from the next login, or after `systemctl --user restart nod-driver-<hash>.service`.

On Linux, installing and removing the job were checked live under WSL with Ubuntu 24.04: the `systemd --user` unit was started with `enable --now`, and the crontab line was written and removed. The core test suite also ran there, on Python 3.12, below the 3.13 that Nod requires. Starting at login or after a reboot was not tested. The macOS job is covered by tests only.

## Stopping, and working without a network

Ctrl+C stops the loop, or `nod driver once`, and kills the agent command it started.

To take a card out of the queue, run `nod card return <id> --note "<why>"`: the card gets an open `return` decision and the driver leaves it alone. If a brief of that card is going on, the brief finishes, but its result is not written.

A card that is `running` can be returned the same way. `nod card return` stops its open run with the result `stop` in the same commit, so the next card's run is not held up. The agent command of that step keeps going until it ends; the driver then drops its result and logs that the run changed, while the commits the agent made stay on the branch. To kill the agent command at once, press Ctrl+C in the driver as well.

With `push = false` the driver needs no network, apart from what `claude` itself needs. With `push = true` and no network the pull fails, so the pass ends as `stale` and starts nothing. If the network drops during a run, the heartbeat fails, the log says so, and the run goes on. A command that ends while the state is stale leaves its result in `.nod/driver/`, the log names the file, and the card stays where it was.

## If the driver is silent

Look for the last `pass:` line in `.nod/driver.log`, or at what `nod driver once` prints.

- `stale: the state has been stale since …`, and higher up `push failed`: the remote moved ahead and a fast-forward pull is not possible. Run `git pull --rebase` in the main worktree; the next pass goes on by itself.
- `lock-lost: dirty tree: <files>`: `.nod/` has uncommitted changes. Commit or remove them.
- `busy: the driver is already running (pid N)`: another driver runs on this machine. A pid file left by a dead process is removed by the driver itself. Delete `.nod/driver/pid` only when N now belongs to some other program.
- `foreign: work in progress on <machine> since <time>`: the other machine holds the lock. It frees itself an hour after the last heartbeat.
- `brief` with `brief <card>: failed, see driver.log`, or the same for `run` or `accept`: the lines above it in the log say why. The output of the command is in `.nod/driver/<card>.<kind>.out.txt` and `.err.txt`.
