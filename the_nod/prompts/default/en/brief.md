Write the brief of the card "{title}" (`{card}`) in the repo `{root}`.
The card body is below, in this prompt.

1. Unless you write `blocked`, make your second-to-last action a commit of the brief to the current branch: `git add <path>`, then `git commit -m "docs(brief): <slug>"`.
2. As your last action, write the line `brief = "<brief path from the repo root>"` to `{result}`.

First read the file `{answers}`. It holds the owner's answers to past questions. The file may be missing.

You work in the repo root already: run commands from it, without `cd` and without `git -C`.
The default allowlist lets Bash run these commands, one command per call: `git status`, `git status --short`, `git log --oneline -20`, `git log -5`, `git diff`, `git diff --stat`, `git diff --cached`, `git add <path>`, `git commit -m "<message>"`, `nod …`.
Read and search files with the Read, Grep and Glob tools.
A denied command does not end the brief: do the same with an allowed command or tool.

Before you ask, read `README.md`, `CONTEXT.md`, `.nod/cards/` and `docs/`.
If the repo has the answer, do not ask the question.

Write the brief by the template below, all ten sections.
Put the file in `docs/briefs/<date>-<slug>.md`.

Brief template:

```
# <Pain title in 4–8 words>

Date: YYYY-MM-DD. Status: draft | approved YYYY-MM-DD | rejected | postponed | split YYYY-MM-DD.

## 1. Pain
<The owner's quote, as said.>

## 2. Verdict
Do | Don't do | Postpone. <One line why.>

## 3. Cost
Cards: N. Run hours: <per card, comma-separated, e.g. 2, 3, 1>. Paid services: none | <which>.

## 4. Decisions
1. <Decision.> Why: <one line>.
2. Question: <wording>? Proposed: <answer>. Why: <reason>. Options: <option> | <option>.

## 5. For the user
- <What the user will see differently.>

## 6. For the system
- <Schema, API, infrastructure.>

## 7. Risks
- <Risk.> If it fires: <what breaks>.

## 8. Maintain later
- <A service, subscription or data contract that appears and stays.> | Nothing.

## 9. How we check
Account: <which>. Steps:
1. <Action.>
2. <Action.>
See: <what>.
For a number: metric <name>, now <value>, threshold <value>.
Keep one: the steps for a scenario or the metric line for a number. For an API, a request instead of the account.

## 10. Steps
1. <Step title in the imperative, no period>
2. …

Outside the run: <who> — <what>.
```

Ask the owner questions only as `Question:` lines in section 4. Do not ask questions in the chat answer.
The line form: `N. Question: <wording>? Proposed: <answer>. Why: <reason>. Options: <option> | <option>.`
The "Proposed:" field is required. Propose the most likely answer.
Start the question wording with a capital letter.
In "Options:" write only the other answers. The proposed answer goes first by itself; do not repeat it in other words.

If the brief needs what only the owner can give, do not guess and do not ask in the chat.
Only the owner gives a login, an API key, a test card. Only the owner brings back a test environment that is down.
Then write one line to `{result}` and stop:
`blocked = "<what the owner must do, in one phrase>"`

Caution: the driver itself opens an `owner-action` decision from the `blocked =` line. If you wrote `blocked`, do not also run `decision ask`: there would be two decisions.

Do not push.
Answer in the chat with one word.
The last two actions are the commit `docs(brief): <slug>` and the line `brief = "<brief path from the repo root>"` in `{result}`.
