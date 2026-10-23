"""English messages of the driver: its log, the decisions it asks, the answers file and the brief parser.

Literal braces are doubled (`{{name}}`): every message goes through `str.format`.
"""

MESSAGES = {
    # one pass and the loop
    "driver.pass": "pass: {did} — {message}",
    "driver.stopped": "stopped by the owner",
    "driver.stale": "the state has been stale since {since}",
    "driver.busy": "the driver is already running",
    "driver.busy_pid": "the driver is already running (pid {pid})",
    "driver.rebrief": "rebrief {card}",
    "driver.failed": "{action}: failed, see driver.log",
    "driver.too_many_reactions": "more than {limit} reactions in one pass: the rest go to the next pass",
    "driver.nothing_to_do": "nothing to do",
    "driver.dirty_tree": "dirty tree: {paths}",
    "driver.pass_aborted": "pass aborted: {error}",
    "driver.other_host": "the driver of this project runs on {host}",
    "driver.dry_run_autostart_only": "--dry-run works only with install and uninstall: a pass runs the agent",

    # the lock
    "driver.foreign": "work in progress on {host} since {at}",
    "driver.push_failed": "push failed",
    "driver.lock_not_taken": "lock not taken: {reason}",
    "driver.heartbeat_stale": "the state is stale",
    "driver.heartbeat_foreign": "foreign lock",

    # decisions the driver asks and its reactions to the answers
    "driver.pain_question": "The backlog is empty. What hurts?",
    "driver.batch_question": "Start the next batch? Cards: {n}.",
    "driver.asked_batch": "asked about the next batch: {id}",
    "driver.asked_pain": "asked what hurts: {id}",
    "driver.owner_note": "Owner's note: {note}",
    "driver.return_reason": "Why the card came back: {reason}",
    "driver.forks_as_proposed": "forks of {card} accepted as proposed: ready",
    "driver.answer_unknown": 'the driver does not understand the answer "{answer}" to {kind} {id}: marked consumed',
    "driver.batch_started": "batch started: {cards}",
    "driver.pain_card": 'card {card} made from the "what hurts" answer',
    "driver.decision_unreadable": "decision {id} is unreadable: {error}",
    "driver.reaction_skipped": "decision {id}: card {card} is {status}, reaction skipped",

    # the answers file the agent reads
    "driver.answers_title": "# Owner's answers on the card {title}",
    "driver.answers_none": "No answers.",
    "driver.answer": "Answer: {answer}",

    # what only the owner can do
    "driver.auth_needed": "Log in to claude: run claude /login in a terminal. The claude answer: {text}",
    "driver.owner_action_reason": "the {kind} command waits for an owner action",
    "driver.waits_owner": "{kind} {card} waits for the owner: {text}",
    "driver.waits_owner_note": "waits for the owner: {text}",
    "driver.kind_brief": "brief",
    "driver.kind_run": "run",
    "driver.kind_accept": "acceptance",

    # the agent command
    "driver.output": "output {kind} {card}: code {code}, {seconds} s, files {out}, {err}",
    "driver.output_not_saved": "output {kind} {card} is not saved: {error}",
    "driver.claude_summary": "claude result {kind} {card}: {summary}",
    "driver.claude_line": "subtype {subtype}, is_error {is_error}, terminal_reason {reason}, turns {turns}, $ {cost}",
    "driver.spend": "spend {kind} {card}: tokens {tokens}, minutes {minutes}, $ {cost}",
    "driver.spend_dirty": "spend {kind} {card} is not written to usage/: agent edits are left in .nod",
    "driver.spend_not_written": "spend {kind} {card} is not written to usage/: {error}",
    "driver.command_stuck": "the command hung: no output for longer than the limit",
    "driver.command_spawn_failed": "the command did not start: {error}",
    "driver.command_exit": "the command exited with code {code}",
    "driver.command_exit_tail": "the command exited with code {code}: {tail}",
    "driver.hooks_dropped": "the agent put files into the hooks folder {folder}: removed",
    "driver.hooks_changed": "the agent changed .git/hooks or the git config: {names} — check and delete",
    "driver.unwritable": ("the owner decision is not written: agent edits are left in .nod; "
                          "the next pass will refuse on a dirty tree"),
    "driver.restore_not_committed": ("the restore of {names} is not committed: the state is stale, "
                                     "the file is restored locally"),
    "driver.card_unreadable": "card {card} is unreadable: {error}",

    # the brief
    "driver.brief_not_started": "brief {card}: command not started: {error}",
    "driver.brief_started": "brief {card}: command started",
    "driver.brief_stale": "the state is stale: the brief result of {card} is not written, file {file}",
    "driver.brief_local": "brief {card}: written locally, push failed",
    "driver.brief_saved": "brief {card}: {status}, steps {steps}, forks {forks}",
    "driver.brief_failed": "brief {card} failed ({n}/{max}): {reason}",
    "driver.brief_failed_returned": "brief {card} failed ({n}/{max}): {reason}; card returned",
    "driver.brief_failed_note": "brief failed: {reason}",
    "driver.card_gone_brief": "card {card} disappeared during the brief, the result is in {file}",
    "driver.card_changed_brief": "card {card} changed during the brief: {status}, the result is not written",

    # a brief the agent wrote but did not commit or report
    "driver.brief_file_unreadable": "brief file {path} is unreadable: {error}",
    "driver.brief_not_committed": "brief {path} is not committed: {error}",
    "driver.candidate_not_found": "brief candidate not found: {error}",
    "driver.candidate_rejected": "brief candidate {path} is not accepted: {error}",
    "driver.previous_result_rejected": "brief {card}: the result of the last attempt is not accepted: {error}",
    "driver.previous_result_adopted": "brief {card}: adopted the result of the last attempt: {path}",
    "driver.previous_brief_rejected": "brief {card}: the brief {path} of the last attempt is not accepted: {error}",
    "driver.previous_brief_adopted": "brief {card}: adopted the brief of the last attempt: {path}",
    "driver.no_result_adopted": "brief {card}: no result, adopted the brief {path}",
    "driver.no_result_adopted_after": "brief {card}: no result, adopted the brief {path} (command: {failure})",

    # the run of a step
    "driver.no_run_reason": "the card is running without a run",
    "driver.hooks_note": "the agent changed .git/hooks or the git config",
    "driver.stop_note": "the agent stopped the run without a note",
    "driver.minutes": "{n} minutes",
    "driver.stuck_note": "hung: {minutes} without a record",
    "driver.stuck_reason": "{minutes} without a record in the run",
    "driver.stuck_question": "The run hung: {title}",
    "driver.run_not_started": "run {card}: not started: {error}",
    "driver.run_started": "run {run} of card {card}, step {step}: command started",
    "driver.run_stale": "the state is stale: the result of run {run} is not written, file {file}",
    "driver.run_unbuilt": "the run command is not built: {reason}",
    "driver.run_return_local": "run {card}: the return is written locally, push failed",
    "driver.run_returned": "run {card}: {note}; card returned",
    "driver.run_unreadable": "run {run} is unreadable: {error}; the result is in {file}",
    "driver.run_changed": "run {run} changed during the command: card {status}, the result is not written",
    "driver.run_local": "run {run}: written locally, push failed",
    "driver.run_ok": "run {run} of card {card}: ok, card {status}",
    "driver.run_of_card": "run {run} of card {card}: {note}",
    "driver.card_running_no_run": "card {card} is running without a run",
    "driver.card_gone_run": "card {card} disappeared during the run, the result is in {file}",
    "driver.written_local": "{summary}: written locally, push failed",
    "driver.card_returned": "{what}; card returned",
    "driver.stuck_stale": "the state is stale: the hang of card {card} is not written",
    "driver.stuck_not_written": "the hang of card {card} is not written: {error}",
    "driver.stuck_wrong_status": "card {card} is {status}, the hang is not written",
    "driver.stuck_wrong_run": "run {run} is not on card {card}, the hang is not written",

    # the acceptance
    "driver.accept_wrong_status": "acceptance {card}: the card is {status}, command not started",
    "driver.accept_unbuilt": "the acceptance command is not built: {error}",
    "driver.accept_note": "acceptance {card}: {text}",
    "driver.accept_started": "acceptance {card}: command started",
    "driver.accept_stale": "the state is stale: the acceptance result of {card} is not written, file {file}",
    "driver.accept_failed_evidence": "acceptance failed: {reason}",
    "driver.accept_not_written": "acceptance {card} is not written: {reason}; {error}",
    "driver.accept_local": "acceptance {card}: written locally, push failed",
    "driver.accept_done": "acceptance {card}: the verdict waits for the owner",
    "driver.accept_failed": "acceptance {card} failed: {reason}; the verdict waits for the owner",
    "driver.card_gone_accept": "card {card} disappeared during the acceptance, the result is in {file}",
    "driver.card_changed_accept": "card {card} changed during the acceptance: {status}, the result is not written",
    "driver.frame_outside": 'frame outside the repo: "{path}"',

    # the guard of the agent command
    "driver.name_hooks": "the hooks folder",
    "driver.name_state": "the .nod state",
    "driver.name_state_failed": "the .nod state (not restored)",
    "driver.name_git_config": "git config",
    "driver.guard_hooks": "the agent put hooks into the driver folder — check",
    "driver.guard_state": "the agent changed the .nod state — restored, check",
    "driver.guard_manifest_origin": "the agent changed harness.toml — the origin version is restored, check",
    "driver.guard_manifest_local": ("the agent changed harness.toml — the version from the snapshot before "
                                    "the command is restored, check"),
    "driver.state_not_restored": "the state is not restored: {paths}",
    "driver.rollback_error": "the rollback gave an error, but the tree is clean: {paths}",
    "driver.check_failed": "the check of {name} failed: {error}; counted as a violation",

    # result files and placeholders
    "driver.result_missing": "no result file",
    "driver.result_no_field": "no field {field}",
    "driver.result_not_strings": "invalid {field}: expected a list of strings",
    "driver.bad_brief_path": "invalid brief path: {path}",
    "driver.unsafe_placeholder": "invalid character in placeholder {{{name}}}",
    "driver.prompt_card": "## Card",

    # the brief parser
    "briefs.no_title": "no title (a `# …` line)",
    "briefs.no_date": "no brief date (a `Date: …` line)",
    "briefs.no_status": "no brief status (a `Status: …` line)",
    "briefs.fork_without_proposed": 'a fork without "Proposed:": {line}',
    "briefs.no_steps": "the brief has no steps (section 10)",
}
