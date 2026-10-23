# X thread

Draft, not posted. Seven posts, each under 280 characters with every link counted at full length (X counts a link as 23).

## 1

Nod is a decision queue for agent-driven development. Claude Code agents write the briefs and the code and check the result. You answer the decisions they can't make.

Open source, MIT: https://github.com/maksim9980/the_nod

## 2

A card goes: brief, your decisions, runs, acceptance, your verdict. Each open question in a brief reaches you with a proposed answer. The driver never answers a decision for you, and the agents it starts can't either.

## 3

The state is Markdown files in .nod/, committed to git on a work branch, so git log is the project history. The core is Python 3.13 with the standard library only. Nod never touches a git remote unless you set [git] push = true.

## 4

Field test on astpretty, a library of about 500 lines Nod had never seen: a --version flag took 15 agent commands and 3.27 USD. Two runs stopped; the card was rebriefed. The test found 4 bugs in Nod, now fixed.

https://github.com/maksim9980/the_nod/blob/main/docs/field-test.md

## 5

It costs money. Every brief, run and acceptance is one claude -p call, capped by default at 5, 30 and 10 USD. Your own global Claude Code plugins and hooks run inside those agents, and Nod doesn't count their spend.

## 6

The pane is built on the new Claude Code mod API. Known bug: the first click on the pane only gives it the focus. It's on the Claude Code side:

https://github.com/maksim9980/the_nod/blob/main/docs/bugs/2026-10-21-pane-first-click-focus.md

## 7

Claude Code only. Checked on Windows 11. Linux, live under WSL: core tests (Python 3.12, Nod needs 3.13) and autostart install; start at login not tested. macOS: tests only.

Install:
claude plugin marketplace add maksim9980/the_nod
claude plugin install nod@nod
