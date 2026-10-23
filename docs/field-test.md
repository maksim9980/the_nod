# Field test: astpretty

One full driver loop of the `default` adapter on a small open-source project that Nod had never seen.
The owner's part, answering decisions, was played by hand with `nod decision answer`.
The test ran on 2026-10-22.

## Project

| | |
|---|---|
| Name | astpretty |
| URL | https://github.com/asottile/astpretty |
| License | MIT |
| Commit | `1fb4135054e6ef00173f556908c17e6807d26c52` |
| Size | about 500 lines of Python, no runtime dependencies |
| Tests | 22 tests with pytest, 0.14 s, no network |
| Console command | `astpretty`; `--version` fails with `unrecognized arguments: --version`, exit code 2 |

The clone lived in a temporary folder. `origin` was removed right after the clone, the work went
to a new branch `nod-field`, and the repo got a local git identity. Nothing was installed with pip:
neither Nod nor the project.

## Environment

- Windows 11 Pro.
- Python 3.13.7.
- Claude Code 2.1.306.
- Adapter `default`, model `sonnet`.
- The core ran as a file, `python -P <core>/the_nod/__main__.py`.
- `nod init` wrote `adapter = "default"` and `[git] push = false` into `harness.toml`.

## The card

```
nod card add "Add a --version flag to the CLI" --body "The astpretty command should accept --version,
print the program name and its version (for example: astpretty 3.0.0) and exit with code 0.
The other options and the output for a file stay as they are."
```

## Passes

Time is the wall time of `nod driver once`. Cost is the `total_cost_usd` of the agent command.

| # | Pass line | Time | Cost, USD | What happened |
|---|---|---|---|---|
| 0 | `brief: brief c-rqus` | 36 s (log) | 0.30 | `driver once --dry-run` ran a real brief (bug 1). Brief with 3 steps and 1 fork; card `waiting-owner`. |
| 1 | `idle: nothing to do` | 0 s | — | The fork waits for the owner. |
| | | | | Owner: fork answered with an option that is not the proposed one. |
| 2 | `react: rebrief c-rqus` | 41 s | 0.22 | Repeat brief edited the same file; 4 steps, no forks; card `ready`. |
| 3 | `run: run c-rqus` | 46 s | 0.23 | Step 1: a failing test for `--version`, committed; `nod run progress` worked. |
| 4 | `run: run c-rqus: failed, see driver.log` | 31 s | 0.22 | Step 2: two Bash denials, the agent wrote `stop`; card `returned` (bug 2). |
| | | | | Fix 2 in place. Owner: `rerun`. |
| 5 | `react: rebrief c-rqus` | 31 s | 0.23 | Repeat brief; 5 steps; card `ready`. No denials. |
| 6 | `run: run c-rqus` | 21 s | 0.18 | Step 1: both tests run and fail, as the step says. |
| 7 | `run: run c-rqus` | 52 s | 0.24 | Step 2: the `--version` option in `main()`. |
| 8 | `run: run c-rqus: failed, see driver.log` | 32 s | 0.20 | Step 3: the new test needs an installed package; pip is not allowed; `stop`. A brief issue, not a core one. |
| | | | | Owner: `rerun` with a note: patch the version lookup in the test. |
| 9 | `react: rebrief c-rqus` | 50 s | 0.25 | Repeat brief; 5 steps; section 9 rewritten for a checkout without install. |
| 10 | `run: run c-rqus` | 42 s | 0.23 | Step 1: test patched, committed. |
| 11 | `run: run c-rqus` | 47 s | 0.20 | Step 2: found the option that pass 7 had left uncommitted, ran the suite, committed it. |
| 12 | `run: run c-rqus` | 33 s | 0.20 | Step 3: the two tests pass. |
| 13 | `run: run c-rqus` | 28 s | 0.18 | Step 4: the whole suite passes, 24 tests. |
| 14 | `run: run c-rqus` | 27 s | 0.19 | Step 5: nothing left to commit, the test and the change were in already; card `accepting`. |
| 15 | `accept: accept c-rqus` | 22 s | 0.20 | Acceptance `solved`, level 2; a `verdict` decision for the owner. |
| | | | | Owner: verdict `accept`; the answer itself made the card `done`. |
| 16 | `pain: pain d-tl74` | 1 s | — | Backlog empty: "What hurts?" asked. Left open. |

## Forks and answers

| Decision | Question | Proposed | Given |
|---|---|---|---|
| fork | What should `--version` print when the package is not installed (running `astpretty.py` from a checkout)? | Let the `PackageNotFoundError` propagate | Print `astpretty unknown` (an option, not the proposed one), note: the owner runs it from a checkout |
| return | Return: Add a --version flag to the CLI | rerun | rerun |
| return | Return: Add a --version flag to the CLI | rerun | rerun, note: do not install; patch `importlib.metadata.version` in the test |
| verdict | Accept the verdict: Add a --version flag to the CLI | accept | accept |

## What worked

- `nod init` on a fresh branch: the manifest, `push = false`, the `.gitignore` lines, the `state: init` commit.
- The brief: all ten sections in English, a well-formed `Question:` line, the commit `docs(brief): …`, the result file.
- An answer outside the proposed one started a repeat brief, and the agent fixed the same file
  after reading the answers file.
- The `nod` wrapper: the agents ran `nod --root … run progress …` from the Claude Code Bash tool
  with no `nod` installed on the machine; each call became a `state: run progress …` commit.
- The step runs, the `stop` results, the `return` decisions and `rerun` with a repeat brief.
- The acceptance ran step 3 of section 9 (`python -m pytest tests`, 24 passed). Step 1
  (`python astpretty.py --version`) was denied, and it ran `python -m pytest tests -k version -v` instead; step 2 it
  did not run. It gave `solved` without seeing the command's output, and said so in its evidence.
- `nod status`, `.nod/driver.log` and `.nod/driver/*.out.txt` told what happened after every pass.
- The driver commits only `state: …` subjects; the agents commit the brief and the code.

## Network and push

- `git remote -v` was empty for the whole test.
- `.nod/driver.log` has no push, pull or fetch line.
- 46 Bash calls of the agents: none ran `git push`, `pull`, `fetch` or `remote`. No permission denial
  was about `git push`: the agents never tried it.

## What broke and how it was fixed

1. **`nod driver once --dry-run` ran a real pass.** `--dry-run` only works with `install` and `uninstall`,
   but the help showed it next to `once` as "show what would be done". The first pass of this test was meant
   as a preview and spent 0.30 USD on a real brief. Without `--passes`, `nod driver --dry-run` would loop.
   Fix: `--dry-run` without `install` or `uninstall` is refused with exit code 2 and no agent starts;
   the help says "with install or uninstall". Commit `fix: refuse driver --dry-run outside install and uninstall`.
   Repeated in the field: `nod driver once --dry-run` now prints
   `error: --dry-run works only with install and uninstall: a pass runs the agent`.
2. **A run step stopped on its first two Bash calls.** The agent ran `cd <repo>; …; git log --oneline | head`
   and `git -C <repo> status --short; python -m pytest …`. Claude Code denied both: a version-control command
   after `cd`, and a `git` form outside the allowlist. Its denial text says that anything needing approval
   will be denied for the rest of the session, so the agent wrote `stop`. The prompts never said that the
   agent already works in the repo root, or which commands the allowlist lets through.
   Fix: the brief, run and accept prompts (both languages) say to work from the repo root without `cd`
   and `git -C`, list the commands the default allowlist lets through, point to the Read, Grep and Glob
   tools, and say that a denied command does not end the step. A test keeps the list in step with the
   adapter's allowlist. After the fix, the 11 agent commands had one denial: the acceptance tried the
   project's own command, which its allowlist does not hold, and went on with the tests.
   Commits `fix: name the allowed commands in the agent prompts` and
   `fix: agent prompts call the command list the default allowlist`.
3. **The stop cause reached the repeat brief as the owner's words.** For a return it opened itself
   (a stopped run, a run command that cannot be built, a brief that failed twice), the driver wrote its
   own text into the decision's `note`. The owner answered `rerun` without `--note`, the note stayed, and
   the repeat brief got "Owner's note: … Bash was denied (no approval surface)", text the owner never wrote
   and by then false. The pane, which shows `reason`, showed no cause at all.
   Fix: the driver writes its text into `reason`; `note` is only the owner's. The repeat brief gets
   "Why the card came back: …" and, when the owner wrote one, "Owner's note: …". The weekly review finds
   failed briefs by `reason`, and by `note` in an older state.
   Commit `fix: driver writes why a card came back into reason, not the owner's note`.
   Found from this test; the loop itself ran before the fix.
4. **`nod init` left the `.gitignore` edit uncommitted and said nothing.** It still leaves the edit to the
   owner, and now prints `.gitignore updated, not committed: commit it yourself`.
   Commit `fix: nod init says the .gitignore edit is not committed`.

## Result

- Card `c-rqus` is `done`; acceptance `solved`, level 2; verdict `accept`.
- In the project: `astpretty.py` gets `--version` with an `unknown` fallback when the package is not installed;
  two new tests; the suite has 24 tests and passes. A checkout prints `astpretty unknown`, exit code 0.

## Spend

- 15 agent commands of the driver: 3.27 USD (4 briefs, 10 step runs, 1 acceptance).
- One manual probe of the agent's `PATH`, outside the driver: 0.27 USD.
- Total: 3.54 USD, the cap was 40 USD.
- Not counted: user-level Claude Code plugins and hooks run inside the agent sessions. On this machine
  a security review plugin started 4 extra sessions on another model, about 70,000 tokens; Nod's spend
  lines do not see them.

## Notes for later

- 2 of the 3 code commits got a `Co-Authored-By` line. It came from the agent and the user's Claude Code
  settings, not from Nod: the run prompt says nothing about attribution. The brief prompt used to forbid
  the line; now no prompt speaks of it, and the user's settings decide
  (`fix: brief prompt leaves commit attribution to the user's settings`).
- A stopped run's uncommitted edits survive the return and the repeat brief. Here later steps built on them
  (pass 11 committed what pass 7 left). With a `backlog` answer the tree would stay dirty.
- The accept allowlist has no way to run the project's own command, so section 9 steps like
  `python astpretty.py --version` cannot run; the acceptance falls back to the tests.
- The agents load the user's own Claude Code setup: `CLAUDE.md`, plugins and hooks. On this machine the chat
  answers of 10 agents out of 15 came back in another language, while the files the agents wrote stayed in English.
- A card in `returned` is not shown in any `nod status` section; only its decision is.

## Not covered

- Linux and macOS in a field test. Outside it, Linux was checked live under WSL with Ubuntu 24.04: the core test suite on Python 3.12 (below the 3.13 that Nod requires), and installing and removing the autostart (a `systemd --user` unit started with `enable --now`, a crontab line written and removed). Starting at login or after a reboot was not tested. macOS is covered by the test suite only.
- The pane on screen.
- Two machines with `push = true`.
- Autostart of the driver.
- A brief that stops with `blocked`, an `owner-action` decision, a hung run.
