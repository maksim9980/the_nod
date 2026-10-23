Check the result of the card "{title}" (`{card}`) in the repo `{root}`.
Do section 9 of the brief `{brief}` literally, step by step.
Do not read the code. Do not read the plan.

First read the file `{answers}`. It holds the owner's answers. The file may be missing.

You work in the repo root already: run commands from it, without `cd` and without `git -C`.
The default allowlist lets Bash run these commands, one command per call: `git status`, `git status --short`, `git log --oneline -20`, `git log -5`, `git diff`, `git diff --stat`, `git diff --cached`, `python -m pytest`, `python -m pytest <args>`, `python3 -m pytest`, `python3 -m pytest <args>`, `nod …`.
Read and search files with the Read, Grep and Glob tools.
A denied command does not end the check: do the same with an allowed command or tool.

Save frames as PNG or JPEG files in the `docs/briefs/` folder next to the brief. Each file is 300 KB or less.
In `frames.path`, write the frame path from the repo root `{root}`.
Do not change the code.

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
- `level = 1`, `2` or `3` — how deep you checked.
- `result = "solved"`, `"unsolved"` or `"unverified"`.
  `solved` — the task is solved. `unsolved` — the task is not solved. `unverified` — the check was not possible.
- `evidence` — what exactly you saw, in one or two phrases.
- `frames = []` — the list of frames; an item is `{ path = "docs/briefs/shot.png", caption = "…" }`, the path from the repo root and a caption.
- `steps = [...]` — the steps of section 9 that you did.
- `report` — the path to the report, if there is one.
Answer in the chat with one word.
