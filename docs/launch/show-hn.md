# Show HN

Draft, not posted. Hacker News shows the text as plain text, so it has no Markdown in it.

## Title

Show HN: Nod – a decision queue for agent-driven development

## URL

https://github.com/maksim9980/the_nod

## Text

Nod is for projects where Claude Code agents write the code and the owner only makes decisions.

Each task is a card. A driver on your machine has an agent write a brief; each open question in it comes to you as a decision with a proposed answer. Then the driver runs the steps, one claude -p call each, and another agent checks the result against the brief. You close the card or send it back. The driver never answers a decision, and its agents can't.

The state is Markdown files in .nod/, committed to a work branch, so git log is the project history. The core is Python 3.13, stdlib only, with no network code. It touches git remotes only with [git] push = true. A pane in Claude Code shows what waits for you; nod status and an MCP server work without it.

Field test: on astpretty, a library of about 500 lines, a --version flag took 15 agent commands (4 briefs, 10 step runs, 1 acceptance) and 3.27 USD. Two runs stopped and went back for a new brief. The test found four bugs in Nod, all fixed: https://github.com/maksim9980/the_nod/blob/main/docs/field-test.md

Limits:

- Claude Code only. Runs cost money. Default caps: 5 USD per brief, 30 per run, 10 per acceptance. Your global Claude Code plugins and hooks run inside the agents, and Nod doesn't count their spend.

- The pane uses the Claude Code mod API, which is new and may change. The first click on the pane only focuses it, a Claude Code bug: https://github.com/maksim9980/the_nod/blob/main/docs/bugs/2026-10-21-pane-first-click-focus.md

- Nod has been run on Windows 11. Linux, live under WSL: the core tests on Python 3.12 (Nod needs 3.13) and installing and removing the autostart (systemd --user, crontab); start at login or reboot not tested. macOS: tests only.
