Do step {step} "{step_title}" of the card "{title}" (`{card}`) in the repo `{root}`.
Work by the brief `{brief}`.

First read the file `{answers}`. It holds the owner's answers. The file may be missing.
Rely on section 10 of the brief and on the decisions of section 4.

You work in the repo root already: run commands from it, without `cd` and without `git -C`.
The default allowlist lets Bash run these commands, one command per call: `git status`, `git status --short`, `git log --oneline -20`, `git log -5`, `git diff`, `git diff --stat`, `git diff --cached`, `git add <path>`, `git commit -m "<message>"`, `python -m pytest`, `python -m pytest <args>`, `python3 -m pytest`, `python3 -m pytest <args>`, `nod …`.
Read and search files with the Read, Grep and Glob tools.
A denied command does not end the step: do the same with an allowed command or tool.

Commit to the current branch. Do not push, do not switch the branch.
After each finished piece, record the progress:
`nod --root "{root}" run progress {run} --contracts-done N`
If no record appears for 40 minutes, the run is stopped.

Caution: a `blocked` line stops the step.
The driver itself opens an `owner-action` decision from it.
Then do not run your own `decision ask`: there would be two decisions.

If the step needs what only the owner can give, do not guess and do not ask in the chat.
Only the owner gives a login, an API key, a test card. Only the owner brings back a test environment that is down.
If the step cannot go on without it, write one line to `{result}` and stop:
`blocked = "<what the owner must do, in one phrase>"`
If the step can go on without it, open the decision yourself:
`nod --root "{root}" decision ask --kind owner-action --card {card} --question "<what the owner must do>" --proposed done --option done --option postpone`
The command prints the decision id. Remember it.
Before you go on with the blocked work, read the decisions with the command:
`nod --root "{root}" decision list --all --json`
Find the decision by its id.
Answer `done` — the owner did it; go on.
Answer `postpone` — the driver sends the card back to the backlog. Do not return to this work. End the step with the answer "postponed by the owner".

As your last action, write TOML to `{result}`:
- `result = "ok"` or `result = "stop"`. If you could not finish the step, write "stop".
- `contracts_total` — how many pieces the step has.
- `contracts_done` — how many pieces are done.
- `note` — one phrase on what is done or why it stopped.
Answer in the chat with one word.
