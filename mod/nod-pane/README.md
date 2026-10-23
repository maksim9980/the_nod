# nod-pane

A Claude Code mod: a "decision queue" pane for a project whose state lives in `.nod/`. The `/nod` command opens the pane.

## Install

The mod is part of the `nod` plugin: the repository root holds the manifest, and `hooks/hooks.json` loads `mod/nod-pane/hooks/register.tsx`. The root README describes how to install the plugin and how to load it while developing.

If there is no `/nod` command, look for lines with `nod:` in `~/.claude/debug/`: they name the reason.

## Language

The pane is English by default. It is Russian when the core writes `"lang": "ru"` into `.nod/state.json`: set `lang = "ru"` in `.nod/harness.toml` or `NOD_LANG=ru` (the variable wins over the manifest). Without the field, or with an unknown value, the pane is English. A new snapshot with another language redraws the pane in it.

Texts outside the pane follow the language of the last snapshot the mod has read: the status line, the `/nod` answers, the transcript lines and the debug log. Before the first snapshot of a session they take the language of the previous load's last snapshot; with none, English.

All texts live in two dictionaries, `hooks/texts/en.ts` and `hooks/texts/ru.ts`; `hooks/texts/index.ts` picks one. The English dictionary sets the shape: the Russian one has the same keys. The values the pane sends to the core are always the canonical English identifiers; only the button labels follow the language.

## How the mod finds nod

At session start the mod tries the candidates in order with `<candidate> --help` and takes the first one that exits with code 0:

1. Your own command from `/config`, field `nod.core`, if it is not empty. Example: `py -3.13 -P <repo>\the_nod\__main__.py`.
2. `python -P <plugin root>\the_nod\__main__.py`.
3. `python3 -P <plugin root>\the_nod\__main__.py`. macOS and stock Ubuntu have `python3` only, no `python`.
4. `py -3 -P <plugin root>\the_nod\__main__.py`.
5. The `nod` command from PATH.

The core runs as a file: `__main__.py` finds the package next to it, so neither pip nor PYTHONPATH is needed. `python`, `python3` and `py` run with `-P`, so that no package from the current folder can replace it.

The `nod.core` field is split into arguments at spaces, so a path with a space cannot go there: use a short path without spaces.

The probes and the core commands run from the plugin root; the project folder takes no part in them.

The probe at session start runs only in a project with `.nod`; `/nod init` and `/nod migrate` look for the core themselves. The command found shows in the second line of the `/nod` answer: `nod: <argv>`. If nobody answered, the `/nod` answer is:

```
nod not found: Python 3.13 is needed (python.org), python, python3 or py in PATH; restart the session after installing
  python -P <plugin root>\the_nod\__main__.py --help — does not start
  python3 -P <plugin root>\the_nod\__main__.py --help — does not start
  py -3 -P <plugin root>\the_nod\__main__.py --help — code N: <first stderr line>
  nod --help — does not start
```

One line per candidate: "does not start" means there is no such program, "code N" means it answered with an error. The pane then says `nod not found: Python 3.13 is needed in PATH; your own command — /config, field nod.core`.

The mod looks for the state from the session folder up to the first `.nod/state.json`, then from the root of the repository's main worktree.

If there is no `.nod/` but the state folder of an older version is found the same way, the `/nod` answer says so, suggests `/nod migrate` and opens the pane with the same line. A session start in such a project opens nothing: a repository that stays on the older version is not nagged.

## /nod subcommands

| Command | What it does | Answer |
|---|---|---|
| `/nod` | opens the pane, prints the diagnostics | see "If a button is silent" |
| `/nod init` | runs `nod --root <repo root> init`, then finds `.nod`, opens the pane and reads the snapshot. The repo root is the main worktree by `git worktree list`; outside a repository — the session folder | `state created: <folder>; pane opened` and the core output |
| `/nod migrate` | runs `nod --root <repo root> migrate` (the older version's state folder becomes `.nod/`), then finds `.nod`, opens the pane and reads the snapshot. The repo root is found as for `/nod init` | `state migrated: <folder>; pane opened`, the core output and its warnings (non-empty stderr lines) |
| `/nod doctor` | runs `nod doctor` for the state found | the core output as is |
| `/nod install` | runs `nod install` for the state found | the core output as is |

For `doctor` and `install` exit code 1 is not an error: that is how the core says "something is missing", and the table comes in full.

Refusals:

- no state — `Nod: no state — no .nod/state.json in <cwd> or above`; `/nod init` creates it. With an older version's state folder the answer is the hint about `/nod migrate`;
- the core refused (`init`, `migrate`: exit code 2 with a message, `migrate` on a protected branch: code 3) — `nod <subcommand> failed: <the core's message>`;
- the core is not found — `core not found — the subcommand did not run`; for `/nod init` and `/nod migrate` a "nod not found" line and the candidates follow;
- the core probe after the start is still running — `the core is still being checked — try again in a few seconds` (for `/nod doctor` and `/nod install`);
- another subcommand — `unknown subcommand: /nod, /nod init, /nod migrate, /nod doctor, /nod install`.

The pane strips the core's error prefix of either language (`error: `, and the Russian one) from a refusal.

## What the pane draws

Five zones from top to bottom, each with a "Name · number" title:

- **Waiting for you** — decisions without an answer: forks and acceptances. A card with a green frame and one main button. An owner-action (something only the owner can do) has a warning frame and the label "Action needed", and comes first.
- **In a run** — cards in work: step, contracts; if the driver holds the lock on another machine — "work in progress on <machine> since <time>".
- **While you were away** — counters since the last visit: runs, steps, accepted, tokens. The first `nod status` at session start marks the visit.
- **Backlog** — the top of the queue and the "Next step" block. An empty backlog suggests "Sort out what hurts".
- **Weekly review** — the last review from `nod review week`. The title is `Weekly review · <week>`, without a review — `Weekly review · —` and the line "No review yet: nod review week". Below: the period, the counters line (runs, steps, stops, accepted, tokens, minutes) and up to five suggestions, the rest as "N more". A suggestion ends in ` · proposed` or ` · applied` (in the snapshot — `proposed` and `applied`); an applied one is dimmed whole. While at least one is proposed, the title is green, the list has a green frame and the button "Apply the suggestions" is under it.

Buttons that write through `nod decision answer` (without the model; after a write the pane rebuilds the snapshot itself):

- a fork option, "Accept all proposed", "Your own answer" (a field, up to 20 words);
- "Done" and "Postpone" of an owner-action; "Yes" and "No" of the next batch; "Wait" of "what hurts"; "Restart", "Rerun" and "To backlog" of a returned or hung run;
- "Confirm — close" and "Accept as is" on an acceptance card;
- "Not right — return" with the field "What is wrong" — writes a decision of kind `return`.

A button sends the canonical identifier to `nod decision answer`: `done` and `postpone` (owner-action), `yes` and `no` (next batch), `wait` ("what hurts"), `accept` and `return` (verdict), `rerun`, `backlog` and `restart` (return, hung run). The label is in the pane's language; a fork option is labelled as is.

Buttons that only build a prompt and put it into the draft do not write the state: "Take the first card", "Show the brief", "Show the backlog", "Name another pain" / "Sort out what hurts", "Suggest a way to check", "Apply the suggestions".

The "Apply the suggestions" prompt asks the agent to open `reviews/<week>.md`, the "What to improve" section, and go through the items with status `proposed`. The agent makes each item a change to the harness rules: the project's `harness.toml`, the adapter prompts in the Nod repository (`the_nod/prompts`) or the project's `CLAUDE.md`. It marks an applied item with `nod --root <.nod> review mark <week> <number> --applied`. What cannot be applied, the agent explains and leaves the status as is.

The "Goes to the chat" footer shows the draft. "Send" queues it through `prompt.submit`, "Clear" wipes it.

Every press goes to the status line under the prompt `Nod: pressed “…”…`; with `diag` on (off by default, see below) also to a grey line in the chat `Nod: pressed “…” · HH:MM:SS` and a toast. Then the status shows `saving <id>…` and the outcome `saved <id> · N ms` (cleared after 5 s) or `not saved <id> — reason`; with `diag` on the outcome repeats as a chat line, an error and a skip also as a toast. The pane footer keeps the line `last action: …` with the outcome: ok, error or `ignored: reason`.

The pane header ends in `· drawn HH:MM:SS · #N`: the time and the number of the drawing by this mod instance. At session start, with `diag` on, the chat gets the line `Nod: mod loaded from <folder> · instance <id> · state reset`: the mod resets its `$.state` keys of earlier loads, except the draft.

While a write runs, the card's buttons are hidden and the line "saving…" shows. An error is written next to it: `not saved: …` and the "Retry" button. The snapshot is reread every 15 seconds and after a tool call.

If the core considers the state not fresh (`git pull --ff-only` failed, detached HEAD), the pane says so in its first line and hides the write buttons. The prompt buttons stay. To get writes back: `git pull` or `git checkout <work branch>`, then "Refresh".

## Checks

The checks of the mod and of the core are in [CONTRIBUTING.md](../../CONTRIBUTING.md#run-the-checks). From the repository root, where the plugin manifest is:

```
claude plugin test .
claude plugin validate .
```

`test` runs the mod's `tests/*.test.ts(x)`. `validate` reads the manifest and the module and names everything Claude Code would refuse.

A demo repository for a manual check. It needs PowerShell 7 (`pwsh`); do not run the script in Windows PowerShell 5.1:

```powershell
pwsh <repo>\mod\nod-pane\tests\demo.ps1 $env:TEMP\nod-demo
python -P <repo>\the_nod\__main__.py --root $env:TEMP\nod-demo status
```

The script creates a git repository with the branch `work`, three cards, one fork, one run and one acceptance with a frame. `status` shows "Waiting for you · 2", "In a run · 1", "Backlog · 3" (the card with the acceptance stays in the queue until the verdict). If the folder exists, the script refuses and touches nothing.

## Check in Desktop

The automatic tests run on a fake world; nobody has checked a live Desktop. Go through the list, tick the items, put the differences into "Known".

Open a new Desktop session in `$env:TEMP\nod-demo` (the plugin installed, see the root README).

- [ ] Open the session. Did the pane open by itself or only after `/nod`? Write down which.
- [ ] Type `/nod`. The second line of the answer is `nod: <command>`, not "nod not found".
- [ ] Open a session in an empty git repository and type `/nod init`. The answer starts with `state created: <folder>; pane opened`, the pane opened, `.nod/` appeared in the repository.
- [ ] After installing the plugin type `/nod doctor`. Its plugin line shows no double load.
- [ ] In the fork press the option that is not proposed. After a few seconds the card is gone, and `git -C $env:TEMP\nod-demo log` shows a commit `state: decision answer …`. If you get `not saved: could not start …` instead, `$.process.run` does not work in Desktop: report it.
- [ ] Open the acceptance card. Is the frame shown as a picture or only as a link? Write down which.
- [ ] Press "Confirm — close". The card is gone and it is not in the backlog.
- [ ] Press "Not right — return", type a text. `python -P <repo>\the_nod\__main__.py --root $env:TEMP\nod-demo decision list` has a new decision of kind `return`.
- [ ] Press "Take the first card", then "Send". The text went to the chat as the first message and holds the card id.
- [ ] In the demo repository run `git checkout --detach`, type `/nod`. The first line is about the stale state, there are no write buttons, the prompt buttons are there. Then `git checkout work` and "Refresh": the write buttons are back.
- [ ] Click the pane and press `1`, `a`, `s`. The hotkeys work while the pane holds the keyboard.
- [ ] Turn on `prefers-reduced-motion` in the system. The mod adds no animations, the behaviour is the host's: no differences.
- [ ] Set `lang = "ru"` in `.nod/harness.toml` of the demo repository and press "Refresh". The pane is redrawn in Russian.

## Known

Not checked in Desktop (the checklist items above):

- Whether the desktop surface docks the pane without the owner asking. If not, the pane opens with `/nod`.
- Whether `$.process.run` works under Desktop. The types mark it "CLI only". If it does not, `nod` is not found ("nod not found"), and every write button answers `not saved: could not start …`.
- Whether `Markdown` on desktop draws a picture from a `file:` address or only a link. Desktop has no `Image` element. If the picture is not drawn, the link to the frame stays.
- The hotkeys `1`, `a`, `s` with the keyboard in the pane.

Other:

- Load the plugin from exactly one place. The installed plugin and the same folder loaded once more past the install give two mod instances in one window: they share the pane and `$.state`, and a press may go to the instance that did not draw the button, so the button is silent. The mod notices it: the pane is drawn by whichever instance the drawing reached — always by itself, writing nothing; the background work (timer, rebuild after a tool) is done by the instance whose token the last `session.start` wrote. If the second one is loaded from another folder, the first line of the pane and the `/nod` answer say `the mod is loaded twice: <folder A> and <folder B> — keep one`. The plugin line of `nod doctor` names the extra load. Remove one of the two loads and restart the session.
- The mod keeps one `nod` process that changes `state.json` at a time (the start `nod status`, the `nod status --peek` of the timer, "Refresh" and re-anchor, `nod decision answer`): the core has no inter-process lock. A click during a rebuild waits for its end, but "saving…" shows at once. The wait is bounded by 70 s: then the write goes on without waiting for the hanging process (`the snapshot rebuild did not finish in 70 s, saving`). A write lock older than `STUCK_AFTER_MS` (about 200 s: the slot wait plus two `nod` limits and a margin, the constants are in `hooks/actions.ts`) counts as stuck: the next click takes it off (`reset a stuck lock (N s)`) and writes.
- The mod looks for the state from the session folder up; it runs `nod` only from the plugin root (a security decision: no package from the project repository is picked up).
- The "While you were away" zone counts from the visit the first `nod status` at the start marks. A write from another session on the same machine moves the count.

## If a button is silent

The first click on the pane gives it focus, the second click acts. When the pane gets the focus, the line `Nod: the pane has focus — a button press will work` shows under the prompt for 3 s. While the pane has no focus, the header has the hint `the first click on the pane gives it focus, the second one acts`. That is how the Desktop surface works, and the mod cannot get around it: opening the pane with the focus at once would take typing and the hotkeys `1`/`a`/`s` from the prompt to the pane. The mod redraws the pane only when the data change, so as not to drop the focus once more.

The `/nod` answer is the diagnostics in one answer: the instance and the plugin root, whether `/nod` is in the engine registry, the pane owner (this instance or another one with its token), `pending`, the last press, the last action, the number of drawings and the time of the last one. It comes even when `$.state` does not answer: the reads are bounded by 2 s.

If the button has the focus and the press is silent, look at the status under the prompt; turn on `diag` to get the grey line in the chat and the toast as well.

- **Nothing at all** — the press did not reach the mod. Type `/nod` and compare the `#N` number in the pane header before and after: if the number did not grow, the surface shows an old frame with dead buttons; close the pane and open it again with `/nod`. If the number grew and the press is silent again, the handler is not called; attach the `/nod` answer.
- **"pressed", but no "saving…"** — the mod got the press, but the write did not start. The status and the footer name the reason (`ignored — saving d-xxxx since HH:MM:SS`, "nod not found", "snapshot not fresh", `pane state does not respond (…)`). If the status is not visible, type `/nod`: the lines `pending:`, `last press:`, `last action:`.
- **`pane state does not respond (…) — going on`** — `$.state` is not written or hangs in this session. The answer is written anyway: "saving…", the write error and the footer live in the module itself, not in `$.state`.

The chat lines and the toasts are off by default. To turn them on: `/config` → `nod.diag` → on. The status under the prompt and the pane footer are always there.

## If there is no /nod command

Even without `/nod` the pane opens by itself after the first message of the session. `/nod` is needed only if the pane was closed.

Look at the load line in the chat: `Nod: mod loaded from … · /nod registered, in the engine registry: yes/no`. The mod writes this line only with `diag` on (off by default): turn on `/config` → `nod.diag` to see the fact.

- **"in the engine registry: yes"** — the engine knows the command, the Desktop command list is out of date. Start a new message. If that does not help, reload the session.
- **"in the engine registry: no — <reason>"** — the line names the reason: a registration error, "the command is not in the list" or "the command list did not answer". The mod repeats the registration right after the session start and once more after the first answer. With `diag` on, each retry with a new outcome writes the line `Nod: registration retry … — …`. No line means the outcome did not change.

If the load line says "yes" and there is still no `/nod`, report it and attach the load line.

## If a button answers slowly

Open the fresh session file in `~/.claude/debug/` and find the `nod:` lines: `nod decision answer — … ms, code …` (how long the process ran), `click <id>: pending +… ms, nod answer … ms, reread +… ms, buttons back +… ms` (offsets from the press), `re-anchor <id> — … ms` and `render — … ms` (written only if a drawing takes longer than 200 ms). A large number at `nod …` means a slow core or its `git commit`: look at `git` in the project repository. A large `render` or large offsets with a small `nod` mean the mod's host calls are slow.
