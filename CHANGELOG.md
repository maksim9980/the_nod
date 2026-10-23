# Changelog

All notable changes to Nod are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.1] - 2026-10-23

### Fixed

- Install instructions use the two documented steps, `claude plugin marketplace add maksim9980/the_nod` and then `claude plugin install nod@nod`. The README, the docs, the `nod doctor` fix for a missing plugin and the launch drafts no longer rely on `claude plugin install --marketplace`, which some Claude Code versions do not offer.

### Changed

- The pane no longer writes diagnostic lines into the chat by default. The load line, the press lines and their toasts appear only when the plugin option `diag` is turned on; the status line and the pane footer stay as before.

### Added

- `.github/workflows/publish.yml` publishes a GitHub release to PyPI with trusted publishing, without API tokens.

## [0.1.0] - 2026-10-22

First release.

### Added

- The `nod` core: cards, decisions, runs, and acceptances stored as files in `.nod/`, a command-line interface, and `--json` output. It is written in Python 3.13 with the standard library only.
- The driver (`nod driver`, and `nod driver once` for a single pass). For each card it works through the brief, the forks, the runs, the acceptance, and the verdict. The agent commands run `claude -p` with a narrow allowlist, a budget cap, and the model `sonnet`.
- Safe defaults for the driver. Git stays local unless `[git] push = true` is set, the agent cannot run `git push` or answer decisions, and git hooks are off while the agent runs. Around every agent command the driver restores uncommitted `.nod/` edits, the manifest, and anything put into the empty hooks folder. It only reports changes to `.git/hooks` and the git config. A finding opens an `owner-action` decision; when uncommitted `.nod/` edits do not roll back, the driver writes nothing and logs an error instead. See [SECURITY.md](SECURITY.md).
- The Claude Code pane and the `/nod` command.
- The `nod` plugin and the `nod` marketplace for Claude Code.
- The MCP server `nod mcp`.
- The weekly review (`nod review`).
- `nod doctor`, which checks what the project needs from the machine, and `nod install`, which sets up what is missing.
- Driver autostart at login on Windows (Task Scheduler), macOS (LaunchAgent), and Linux (`systemd --user` or a crontab `@reboot` line), installed with `nod driver install` and removed with `nod driver uninstall`. On Linux, installing and removing were checked live under WSL with Ubuntu 24.04 (the `systemd --user` unit started with `enable --now`, the crontab line written and removed), and so was the core test suite, on Python 3.12, below the 3.13 that Nod requires. Starting at login or after a reboot was not tested. The macOS setup is covered by tests only.
- English and Russian. English is the default; set `lang = "ru"` in `.nod/harness.toml` or `NOD_LANG=ru` for Russian. The variable wins over the manifest.
- `nod import markdown`, which turns each `##` heading of a Markdown file into a backlog card.
- `nod migrate`, which moves a project with an old `.sprintboot/` state folder over to `.nod/`. `/nod migrate` runs it from Claude Code.

[0.1.1]: https://github.com/maksim9980/the_nod/releases/tag/v0.1.1
[0.1.0]: https://github.com/maksim9980/the_nod/releases/tag/v0.1.0
