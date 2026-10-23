"""English messages of the core: CLI, state files, git, the backlog view and command help.

Literal braces are doubled (`{{card}}`): every message goes through `str.format`.
"""

_HARNESS_TEMPLATE = """\
# Driver manifest: which commands write the brief, run a step and accept a card.
# lang: interface language, en or ru; the NOD_LANG environment variable wins.
lang = "{lang}"
# adapter: the set of driver commands and prompts; only default exists for now.
adapter = "default"
driver_host = ""
# An empty command means the adapter's default command.
# Placeholders in commands: {{card}} {{brief}} {{root}} {{answers}} {{result}} {{prompt}} {{step}} {{run}}.
# {{title}} and {{step_title}} are for prompts only: a command goes to the shell.
# By default the agent has no git push, no branch switching and no python -c; it does run the project's tests, which are code it writes itself. To allow more, write your own command with a different --allowedTools.
# The model in the default commands (--model sonnet) is the owner's choice: change it with your own command.
[commands]
brief = ""
run = ""
accept = ""

[git]
# false: Nod never talks to a remote. true: pull before every write and push after it — needed when the driver and you work from two machines.
push = false

# What the project needs from the machine: nod doctor checks it, nod install sets it up.
# [needs]
# python = "3.13"
# nod: an empty string means no check; the core comes with the plugin.
# nod = ""
# claude = "claude"
# jobs = ["driver"]
# skills = []
# agents = []
# rules = []
"""

MESSAGES = {
    # cli
    "cli.error": "error: {message}",
    "cli.empty": "empty",

    # context
    "context.agent_refused": "this command is not available to the driver's agent",
    "context.stale": "the state has been stale since {since}: run git pull first",
    "context.push_failed": "push failed: {error}",
    "context.not_main_tree": "the state must live in the main worktree: {path}",
    "context.no_state": "no state: run nod init",

    # store
    "store.bad_id": 'invalid id: "{id}"',
    "store.bad_week": 'invalid week: "{week}"',
    "store.duplicate_id": "duplicate id {id}: {first} and {second}",
    "store.not_found": 'no object "{id}" in "{folder}"',
    "store.bad_frame_ext": 'frame: invalid extension "{ext}"',
    "store.bad_toml": "invalid TOML: {error}",

    # model
    "model.not_tables": "invalid {field}: expected a list of tables",
    "model.missing_field": "missing required field: {field}",
    "model.bad_value": 'invalid {field}: "{value}"',

    # frontmatter
    "frontmatter.unclosed": 'frontmatter is not closed by a "+++" line',
    "frontmatter.bad_toml": "invalid frontmatter: {error}",
    "frontmatter.bad_type": "unsupported value type: {type}",
    "frontmatter.bad_list": "a list must hold only strings or only tables",

    # git and paths
    "git.not_found": "git not found",
    "git.detached": "not on a branch: detached HEAD",
    "git.protected_state": 'branch "{branch}" is protected: write the state on a work branch',
    "git.protected_commit": 'branch "{branch}" is protected: commits go to a work branch',
    "git.undo_not_root": "cannot roll back {sha}: it is not the first commit of the branch",
    "git.undo_foreign": "cannot roll back {sha}: the first commit also holds {path}, outside {state}/",
    "paths.git_failed": 'could not run git in "{path}": {error}',
    "paths.not_a_repo": '"{path}" is not a git repository: {error}',
    "paths.no_main_tree": 'git did not report the main worktree for "{path}"',

    # manifest
    "harness.prompt_only": "placeholder {{{name}}} is for prompts only",
    "harness.unknown_placeholder": "unknown placeholder {{{name}}} in the {kind} command",
    "harness.not_string": '"{key}" is not a string',
    "harness.not_table": '"{key}" is not a table',
    "harness.not_bool": '"{key}" is not true or false',
    "harness.unknown_key": 'unknown key "{key}"',
    "harness.unknown_adapter": 'adapter "{adapter}" is unknown: {allowed}',
    "harness.bad_lang": 'lang = "{value}": unknown language, use en or ru',
    "harness.missing": "no manifest .nod/harness.toml: run nod init",
    "harness.bad_toml": "invalid TOML in {path}: {error}",
    "harness.unreadable": "cannot read the manifest {path}: {error}",
    "harness.push_unread": ("warning: cannot read the manifest {path} ({error}):"
                            " Nod stays local, no pull or push, until it is fixed"),
    "harness.no_value": "no value for {{{name}}}",

    # transitions
    "transitions.bad_result": 'unknown result "{result}": {allowed}',
    "transitions.no_run": "card {card} is {status}: a run is not possible",
    "transitions.run_open": "a run is already open: {run}",
    "transitions.no_step": "the card has no step {step}",
    "transitions.run_finished": "the run already finished at {finished}",
    "transitions.run_abandoned": "closed when run {run} started: the card was not running",
    "transitions.progress_line": "{now} contracts done: {done}",
    "transitions.bad_level": "unknown level {level}: 1, 2 or 3",
    "transitions.too_many_frames": "at most six frames, got {count}",
    "transitions.captions_mismatch": "there must be as many captions as frames",
    "transitions.no_frame": 'no frame "{path}"',
    "transitions.verdict_waiting": "a verdict is already waiting for an answer: {decision}",
    "transitions.verdict_question": "Accept the verdict: {title}",
    "transitions.frame_too_big": "frame {path} is over 300 KB, not copied",

    # backlog view (nod render)
    "render.head": "# {title} — printed from .nod",
    "render.warning": "> The source of truth is .nod/. nod render {name} prints this file; edits by hand are lost.",
    "render.active": "## Active tasks (by priority)",
    "render.brief": "Brief: {brief}",
    "render.done": "## ~~{title}~~ — DONE ({date})",
    "render.written": "wrote {path}",

    # nod init
    "init.created": "created {dir} in {parent}",
    "init.gitignore_uncommitted": ".gitignore updated, not committed: commit it yourself",
    "init.protected_branch": ('branch "{branch}" is protected: Nod commits its state on a work branch'
                              " — create one with git switch -c <name>, then run nod init again"),
    "init.harness_template": _HARNESS_TEMPLATE,

    # nod card
    "card.not_found": 'no card "{id}"',
    "card.not_in_backlog": '"{id}" is not in the backlog',
    "card.closed": "card {card} is already closed",
    "card.closed_at": "card {card} is already closed at {closed_at}",
    "card.returned": "card {card} is already returned",
    "card.return_question": "Return for rework: {title}",
    "card.show_status": "status: {status}",
    "card.show_brief": "brief:",
    "card.show_steps": "steps:",

    # nod decision
    "decision.not_found": 'no decision "{id}"',
    "decision.bad_kind": 'unknown kind "{kind}": {allowed}',
    "decision.agent_kind": 'the driver\'s agent cannot ask a "{kind}" decision, only {allowed}',
    "decision.answered": "already answered at {at}",
    "decision.not_an_option": 'answer "{answer}" is not one of the options: {options}',
    "decision.row": "{id}  {kind}  {question}  → proposed: {proposed}",

    # nod run
    "run.not_found": 'no run "{id}"',

    # nod status
    "status.waiting": "Waiting for you · {count}",
    "status.running": "In a run · {count}",
    "status.since": "While you were away · since {since}",
    "status.backlog": "Backlog · {count}",
    "status.counters": "runs {runs} · steps {steps} · accepted {accepted} · tokens {tokens}",
    "status.closed": "closed {id}  {title}  {closed_at}",
    "status.run_row": "{card}  {title}  step {step}: {step_title}  contracts {done}/{total}",
    "status.stale": "The state has been stale since {since}: writes are off, run git pull first",

    # command help
    "help.root": "path to .nod or to the repository root",
    "help.json": "JSON output",
    "help.note": "a note",
    "help.init": "create .nod in the repository",
    "help.card": "work with cards",
    "help.card_add": "add a card to the backlog",
    "help.card_title": "title",
    "help.card_body": "card text",
    "help.card_top": "put it at the top of the backlog",
    "help.card_move": "move a card in the backlog",
    "help.card_close": "close a card",
    "help.card_return": "return a card for rework",
    "help.card_return_note": "what is wrong",
    "help.card_show": "show a card",
    "help.decision": "decisions: questions to the owner",
    "help.decision_list": "show unanswered decisions",
    "help.decision_all": "include answered ones",
    "help.decision_ask": "ask a question (for the driver and agents)",
    "help.decision_kind": "kind: {kinds}",
    "help.decision_proposed": "proposed answer",
    "help.decision_option": "answer option, repeatable",
    "help.decision_answer": "answer a decision",
    "help.decision_answer_value": "the answer",
    "help.decision_free": "an answer outside the options",
    "help.status": "show the state snapshot",
    "help.status_since": "count changes from this moment (ISO)",
    "help.status_no_sync": "do not sync with git",
    "help.status_peek": "do not mark the view in seen.toml",
    "help.run": "runs: start, progress, finish",
    "help.run_start": "start a run for a card",
    "help.run_step": "card step number",
    "help.run_contracts": "number of contracts in the run",
    "help.run_progress": "record the progress of a run",
    "help.run_finish": "finish a run",
    "help.accept": "accept a card: a verdict for the owner",
    "help.accept_level": "check level: 1, 2 or 3",
    "help.accept_evidence": "what confirms it",
    "help.accept_frame": "a frame, repeatable",
    "help.accept_caption": "a frame caption",
    "help.accept_step": "a checked step, repeatable",
    "help.accept_report": "path to the report",
    "help.render": "print the backlog or archive view",
    "help.render_write": "write to a file instead of stdout",
    "help.render_path": "PATH",
    "help.driver": "driver: passes over the cards without a human",
    "help.driver_action": "once: one pass; install, uninstall: install or remove the login autostart; no action: a loop",
    "help.driver_interval": "seconds between loop passes",
    "help.driver_passes": "how many passes, 0 means no limit",
    "help.driver_dry_run": "with install or uninstall: show what would be done",
    "help.review": "weekly review",
    "help.review_week": "collect the review of a period and write reviews/<week>.md",
    "help.review_since": "period start (ISO), a week ago by default",
    "help.review_mark": "mark the status of a review suggestion",
    "help.review_mark_week": "review week, for example 2026-43",
    "help.review_mark_n": "suggestion number",
    "help.review_mark_status": 'status "{status}"',
    "help.doctor": "check the machine: what the project needs and what is missing",
    "help.install": "install what nod doctor finds missing",
    "help.install_dry_run": "show the steps without changing anything",
    "help.mcp": "MCP server over stdio for agents",
}
