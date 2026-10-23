# r/ClaudeAI post

Draft, not posted.

- Image: `docs/launch/panel.png`, the PNG export of `docs/images/panel.svg` (Reddit takes no SVG). The picture is a drawn mock-up of the pane for a made-up project, not a screenshot. Say so in the caption, as below, or replace it with a real screenshot before posting.
- Flair: check the subreddit rules for project posts on the day of posting.

## Title

Nod: Claude Code agents move the project, and a pane shows what only you can decide

## Image caption

The Nod pane, drawn for a sample project: three decisions waiting for the owner, one card in a run, the backlog and the weekly review.

## Body

Nod is an open-source (MIT) plugin and Python core for running a project through Claude Code agents. You write cards. A driver on your machine has an agent brief each card, runs the steps with `claude -p`, and has another agent check the result. Each open question of a brief lands on the pane as a decision with a proposed answer. You click the proposed answer or type your own. The driver never answers for you.

Everything lives as files in `.nod/`, committed to git on a work branch. Nod talks to no git remote unless you turn on `[git] push = true`.

How to try:

1. `claude plugin marketplace add maksim9980/the_nod`, then `claude plugin install nod@nod`. In Claude Desktop, click "+" next to the prompt, open Plugins, add the marketplace `maksim9980/the_nod`, then the `nod` plugin, and restart Desktop.
2. In a repo, make a work branch with `git switch -c nod-work`, then type `/nod init` in a session. It creates `.nod/` and opens the pane. It also edits `.gitignore` without committing it, so commit that yourself.
3. `nod card add "<title>" --body "<what you want>"`
4. Run `nod driver once`, pass after pass, and answer whatever shows up under "Waiting for you".

For `nod` in a terminal, run `pipx install the-nod`. Without it, `/nod` prints the command to use in its place.

Before you try:

- It costs money. Every brief, run and acceptance is one `claude -p` call, capped by default at 5, 30 and 10 USD. In the field test, a `--version` flag for a library of about 500 lines took 15 calls and 3.27 USD. Your own global plugins and hooks run inside those agents, and their spend is not in Nod's numbers.
- The pane is built on the Claude Code mod API, which is new. The first click on the pane only gives it the focus, and the second one presses the button. It's a Claude Code bug, written up here: https://github.com/maksim9980/the_nod/blob/main/docs/bugs/2026-10-21-pane-first-click-focus.md
- Nod has been run on Windows 11. On Linux, under WSL, the core tests ran live on Python 3.12 (Nod needs 3.13), and the autostart was installed and removed (systemd --user, crontab). Start at login or reboot was not tested. macOS has the tests only.
- Claude Code only.

Repo: https://github.com/maksim9980/the_nod

Field test, pass by pass: https://github.com/maksim9980/the_nod/blob/main/docs/field-test.md
