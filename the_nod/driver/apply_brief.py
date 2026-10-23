"""The brief executor: the agent command writes the brief, the forks go to the owner.

The driver never answers decisions: it reads the answers and marks the decisions consumed.
The reactions to answers, the batch and "what hurts" live in `react.py`.
"""

import dataclasses
from collections.abc import Callable
from pathlib import Path

from the_nod import harness as harness_mod
from the_nod import vocab
from the_nod.adapters import briefs
from the_nod.commands.card import make_return_decision
from the_nod.context import Context, Stale
from the_nod.driver import adopt, agent, files, guard, lock, plan, results, shim, usage
from the_nod.driver.log import Log
from the_nod.gitsync import GitError, ProtectedBranch
from the_nod.i18n import t
from the_nod.model import Card, Decision, Spend, Step
from the_nod.transitions import make_decision

CONFIG_NAME = guard.GIT_CONFIG


def append_line(body: str, line: str) -> str:
    return f"{body.rstrip()}\n{line}" if body.strip() else line


def consumed(decision: Decision, now: str) -> Decision:
    """A copy of the decision with the `Consumed:` mark: the planner does not hand it out again."""
    return dataclasses.replace(decision, body=append_line(decision.body, f"{vocab.CONSUMED_MARK} {now}"))


def load_card(ctx: Context, log: Log, card_id: str) -> Card | None:
    try:
        return ctx.store.load_card(card_id)
    except (FileNotFoundError, ValueError) as err:
        log.error(t("driver.card_unreadable", card=card_id, error=err))
        return None


# --- the answers file ---

def fork_answers(forks: list[Decision]) -> list[str]:
    """The answers file items for the forks: the question, the answer and the owner's note."""
    items = []
    for n, d in enumerate(forks, start=1):
        answer = d.answer or ""
        shown = answer if answer.endswith(".") else f"{answer}."
        line = f"{n}. {d.question}\n   {t('driver.answer', answer=shown)}"
        items.append(f"{line} {d.note}" if d.note else line)
    return items


def _write_answers(store, card: Card, answers: list[str] | None, append: list[str]) -> None:
    """The answers file lives through the whole card cycle, up to the backlog.

    `answers` is a new set and rewrites the file; otherwise `append` is added to the file,
    and without a file the text says there are no answers.
    """
    path = files.answers_path(store, card.id)
    if answers is None and path.exists():
        if append:
            text = path.read_text(encoding="utf-8").rstrip("\n")
            path.write_text(text + "\n" + "\n".join(append) + "\n", encoding="utf-8")
        return
    items = answers if answers is not None else append
    body = "\n".join(items) if items else t("driver.answers_none")
    path.write_text(f"{t('driver.answers_title', title=card.title)}\n\n{body}\n", encoding="utf-8")


def forget_cycle(store, card_id: str) -> None:
    """The card went to the backlog: the answers and attempts of the last cycle are not needed any more."""
    files.answers_path(store, card_id).unlink(missing_ok=True)
    files.clear_attempt(store, card_id)


# --- the brief ---

def brief(ctx: Context, harness: harness_mod.Harness, log: Log, card_id: str, *,
          answers: list[str] | None = None, append: list[str] = (),
          consume: tuple[Decision, ...] = ()) -> bool:
    """One brief command. `True` means the brief is written (`ready` or `waiting-owner`).

    `append` holds lines added to the answers file of the cycle; `consume` holds decisions
    marked consumed in the same commit as `briefing`.
    """
    store = ctx.store
    card = load_card(ctx, log, card_id)
    if card is None:
        return False
    try:
        command, prompt, values = render_command(ctx, harness, card, "brief")
    except harness_mod.HarnessError as err:
        log.error(t("driver.brief_not_started", card=card.id, error=err))
        _failed(ctx, log, card, str(err))
        return False
    started = dataclasses.replace(card, status="briefing")
    marked = [consumed(d, ctx.now) for d in consume]

    def apply() -> None:
        store.save_card(started)
        for d in marked:
            store.save_decision(d)

    if not lock.claim(ctx, f"driver brief {card.id} briefing", apply):
        log.warn(lock_refused())
        return False
    adopted = adopt.before_command(ctx, log, harness.briefs_dir, started)
    if adopted is not None:
        _save_brief(ctx, log, started, *adopted)
        return True
    _write_answers(store, card, answers, list(append))
    result = launch(ctx, card, "brief", prompt)
    log.info(t("driver.brief_started", card=card.id))
    outcome, changed = run_agent(ctx, log, command, prompt, values, kind="brief")
    fresh = files.reopen(ctx)
    if not fresh.fresh:
        log.error(t("driver.brief_stale", card=card.id, file=result))
        stale_restore(log, changed)
        return False
    done = _finish(fresh, log, card.id, outcome, changed, result, harness.briefs_dir)
    record_usage(fresh, log, "brief", card.id, outcome, changed)
    return done


def record_usage(ctx: Context, log: Log, kind: str, card_id: str, outcome: agent.Outcome,
                 changed: list[str] = ()) -> None:
    """The spend of a brief or an acceptance goes to the log and to `usage/`; a run keeps its spend in the run.

    It is written for a failed command too: the tokens are spent. A write failure goes only to the log.
    If the state did not roll back (`changed`), nothing is written: the commit would take the agent edits.
    """
    u = usage.measure(outcome.stdout, files.repo_root(ctx.store))
    cost = "—" if u.cost_usd is None else f"{u.cost_usd:.2f}"
    log.info(t("driver.spend", kind=kind, card=card_id, tokens=u.tokens, minutes=u.minutes, cost=cost))
    if guard.STATE_FAILED in changed:
        log.warn(t("driver.spend_dirty", kind=kind, card=card_id))
        return
    spend = Spend(kind=kind, card=card_id, at=ctx.now, tokens=u.tokens, minutes=u.minutes,
                  agents=u.agents, tool_errors=u.tool_errors, cost_usd=u.cost_usd)
    try:
        ctx.write(f"driver usage {kind} {card_id}", lambda: ctx.store.save_spend(spend))
    except (Stale, ProtectedBranch, GitError, OSError) as err:
        log.warn(t("driver.spend_not_written", kind=kind, card=card_id, error=err))


KIND_KEYS = {"brief": "driver.kind_brief", "run": "driver.kind_run", "accept": "driver.kind_accept"}


def kind_name(kind: str) -> str:
    """The word for a command kind in the current language; an unknown kind keeps its own name."""
    return t(KIND_KEYS[kind]) if kind in KIND_KEYS else kind


def lock_refused() -> str:
    """The log line when `lock.claim` refused: its reason, or a failed push."""
    return t("driver.lock_not_taken", reason=lock.last_refusal or t("driver.push_failed"))


def render_command(ctx: Context, harness: harness_mod.Harness, card: Card, kind: str,
                   **extra) -> tuple[str, str, dict[str, str]]:
    """The command, the prompt and the placeholders of `kind`; `HarnessError` if the command cannot be built.

    The caller does not lock the queue: a brief counts the refusal as a failed attempt, a run returns
    the card, an acceptance writes `unverified`. `extra` holds `step` and `run` for `files.placeholders`.
    """
    values = files.placeholders(ctx, card, kind=kind, **extra)
    command = harness_mod.render(harness.commands[kind], files.command_values(values))
    return command, files.prompt_text(harness.adapter, kind, values, card), values


def launch(ctx: Context, card: Card, kind: str, prompt: str) -> Path:
    """The prompt to disk, the old result removed; the path of the result file."""
    files.prompt_path(ctx.store, card.id, kind).write_text(prompt, encoding="utf-8")
    result = files.result_path(ctx.store, card.id, kind)
    result.unlink(missing_ok=True)
    return result


def read_result(reader: Callable[[Path], object], path: Path) -> tuple:
    """The result through `reader` (`results.read_*`) and an empty reason; `(None, reason)` on `ResultError`."""
    try:
        return reader(path), ""
    except results.ResultError as err:
        return None, str(err)


def save_output(ctx: Context, log: Log, kind: str, card_id: str, outcome: agent.Outcome) -> None:
    """The stdout and stderr tails go to `.nod/driver/`, the `claude -p` result to the log: why the agent stopped."""
    try:
        out, err = files.save_output(ctx.store, card_id, kind, outcome)
    except OSError as error:
        log.error(t("driver.output_not_saved", kind=kind, card=card_id, error=error))
        return
    code = outcome.status if outcome.code is None else outcome.code
    log.info(t("driver.output", kind=kind, card=card_id, code=code, seconds=outcome.seconds, out=out, err=err))
    summary = usage.claude_summary(outcome.stdout)
    if summary:
        log.info(t("driver.claude_summary", kind=kind, card=card_id, summary=summary))


def run_agent(ctx: Context, log: Log, command: str, prompt: str, values: dict[str, str], *,
              kind: str, activity: Callable[[], float] = lambda: 0.0) -> tuple[agent.Outcome, list[str]]:
    """The agent command with snapshots of the hooks, the git config and the manifest before and after; the second item is what changed.

    The command gets a `nod` wrapper first on its `PATH` (`shim.py`): the plugin ships the core without pip.
    What the agent touched (the hooks folder, the state, the manifest) is already restored on disk (`guard.py`),
    and the list holds `guard.NAMES` names. The output of the `kind` command is always saved (`save_output`).
    `activity` is the time of the last agent write (epoch): a run passes the mtime of its file.
    """
    store = ctx.store
    root = files.repo_root(store)
    folder = agent.hooks_folder(root)
    hooks_before, config_before = agent.hooks_snapshot(folder), agent.config_snapshot(root)
    reference = guard.snapshot(ctx)
    no_hooks = guard.hooks_dir(root)

    def tick() -> None:
        if not lock.heartbeat(ctx):
            log.warn(f"heartbeat: {lock.last_heartbeat}")

    env = {**files.env_from(values), **shim.agent_env(store)}
    outcome = agent.run_command(
        command, cwd=root, stdin=prompt, env=env,
        activity=activity, stuck_after=plan.STUCK_SECONDS,
        tick=tick, tick_every=lock.HEARTBEAT_SECONDS,
        hooks_dir=no_hooks)
    save_output(ctx, log, kind, values["card"], outcome)
    hooks_after, config_after = agent.hooks_snapshot(folder), agent.config_snapshot(root)
    changed = sorted(n for n in {*hooks_before, *hooks_after} if hooks_before.get(n) != hooks_after.get(n))
    if config_before != config_after:
        changed.append(CONFIG_NAME)
    found = guard.after(ctx, no_hooks, reference, log)
    if guard.HOOKS in found:
        log.error(t("driver.hooks_dropped", folder=no_hooks))
    return outcome, changed + found


def unwritable(log: Log, changed: list[str]) -> bool:
    """The state did not roll back: any write would commit the agent edits, so nothing is written."""
    if guard.STATE_FAILED not in changed:
        return False
    log.error(t("driver.unwritable"))
    return True


def stale_restore(log: Log, changed: list[str]) -> None:
    """The restore is not in a commit: this line explains the next `lock-lost` on a dirty tree."""
    # STATE_FAILED is not restored: its ERROR is already in the log.
    restored = [n for n in changed if n in guard.NAMES and n not in (guard.HOOKS, guard.STATE_FAILED)]
    if restored:
        log.error(t("driver.restore_not_committed", names=", ".join(guard.label(n) for n in restored)))


def tamper_text(ctx: Context, changed: list[str]) -> str:
    """The owner text on what the agent changed: the hooks folder, the state, the manifest, the hooks and the git config."""
    others = [n for n in changed if n not in guard.NAMES]
    parts = [guard.owner_text(changed)] if any(n in guard.NAMES for n in changed) else []
    if others:
        parts.append(t("driver.hooks_changed", names=", ".join(guard.label(n) for n in others)))
    return "; ".join(parts)


def tampered(ctx: Context, log: Log, card: Card, kind: str, changed: list[str]) -> None:
    """The owner decision through a fresh context; what was restored goes into the same commit."""
    if unwritable(log, changed):
        return
    summary = guard.summary(changed, card.id)
    owner_action(ctx, log, card, kind=kind, text=tamper_text(ctx, changed), summary=summary)


def owner_wait(outcome: agent.Outcome, blocked: str) -> str:
    """The owner text: `blocked` from the result or a refused claude login; otherwise empty."""
    if blocked:
        return blocked
    auth = usage.auth_failure(outcome.stdout)
    return t("driver.auth_needed", text=auth) if auth else ""


def outcome_failure(outcome: agent.Outcome) -> str:
    """The failure reason by the process outcome; empty if the command exited with code 0."""
    if outcome.status == "stuck":
        return t("driver.command_stuck")
    if outcome.status == "spawn-error":
        return t("driver.command_spawn_failed", error=outcome.stderr.strip())
    if outcome.code != 0:
        tail = next((ln.strip() for ln in reversed(outcome.stderr.splitlines()) if ln.strip()), "")
        if tail:
            return t("driver.command_exit_tail", code=outcome.code, tail=tail)
        return t("driver.command_exit", code=outcome.code)
    return ""


def _finish(ctx: Context, log: Log, card_id: str, outcome: agent.Outcome,
            changed: list[str], result_file: Path, briefs_dir: str) -> bool:
    card = load_card(ctx, log, card_id)
    if card is None:
        log.error(t("driver.card_gone_brief", card=card_id, file=result_file))
        return False
    if changed:
        tampered(ctx, log, card, "brief", changed)
        return False
    if card.status != "briefing":
        log.warn(t("driver.card_changed_brief", card=card.id, status=card.status))
        return False
    result, error = read_result(results.read_brief, result_file)
    wait = owner_wait(outcome, result.blocked if result else "")
    if wait:
        owner_action(ctx, log, card, kind="brief", text=wait)
        return False
    if result is None:
        # No TOML: a brief the agent wrote and did not commit is adopted as the result.
        failure = outcome_failure(outcome)
        parsed, why = adopt.after_command(ctx, log, briefs_dir, card, failure)
        if parsed is not None:
            _save_brief(ctx, log, card, *parsed)
            return True
        reason = "; ".join(r for r in (failure or error, why) if r)
    else:
        reason = outcome_failure(outcome)
    if not reason:
        try:
            # The agent may have written the result but not committed the brief: the driver commits it.
            parsed = adopt.adopt(ctx, card, result.brief)
        except ValueError as err:
            reason = str(err)
    if reason:
        _failed(ctx, log, card, reason)
        return False
    _save_brief(ctx, log, card, *parsed)
    return True


def _save_brief(ctx: Context, log: Log, card: Card, rel: str, steps: list[str],
                forks: list[briefs.Fork]) -> None:
    store = ctx.store
    status = "waiting-owner" if forks else "ready"
    done = dataclasses.replace(card, status=status, brief=rel,
                               steps=[Step(n=n, title=t) for n, t in enumerate(steps, start=1)])
    decisions = [make_decision(store, kind="fork", question=f.question, proposed=f.proposed,
                               options=list(f.options), reason=f.reason, card=card.id, now=ctx.now)
                 for f in forks]

    def apply() -> None:
        store.save_card(done)
        for d in decisions:
            store.save_decision(d)

    if not ctx.write(f"driver brief {card.id} {status}", apply):
        log.warn(t("driver.brief_local", card=card.id))
    files.clear_attempt(store, card.id)
    log.info(t("driver.brief_saved", card=card.id, status=status, steps=len(steps), forks=len(forks)))


def _failed(ctx: Context, log: Log, card: Card, reason: str) -> None:
    store = ctx.store
    n = files.bump_attempt(store, card.id)
    if n < files.MAX_ATTEMPTS:
        log.warn(t("driver.brief_failed", card=card.id, n=n, max=files.MAX_ATTEMPTS, reason=reason))
        return
    log.error(t("driver.brief_failed_returned", card=card.id, n=n, max=files.MAX_ATTEMPTS, reason=reason))
    back = dataclasses.replace(card, status="returned")
    decision = make_return_decision(store, back, note="", now=ctx.now,
                                    reason=t("driver.brief_failed_note", reason=reason))

    def apply() -> None:
        store.save_card(back)
        store.save_decision(decision)

    ctx.write(f"driver brief {card.id} returned", apply)
    files.clear_attempt(store, card.id)


# --- an owner action ---

def make_owner_action(store, card: Card, *, kind: str, text: str, now: str) -> Decision:
    """An `owner-action` decision, not written: `apply_run` puts it into its own `ctx.write`."""
    return make_decision(store, kind="owner-action", question=text, proposed=vocab.DONE,
                         options=[vocab.DONE, vocab.POSTPONE], reason=t("driver.owner_action_reason", kind=kind),
                         card=card.id, now=now)


def owner_action(ctx: Context, log: Log, card: Card, *, kind: str, text: str, summary: str = "") -> str:
    """A question to the owner about what only the owner can do; the card status does not change."""
    decision = make_owner_action(ctx.store, card, kind=kind, text=text, now=ctx.now)
    ctx.write(summary or f"driver owner-action {card.id}", lambda: ctx.store.save_decision(decision))
    files.clear_attempt(ctx.store, card.id)
    log.warn(t("driver.waits_owner", kind=kind_name(kind), card=card.id, text=text))
    return decision.id


# --- names from `react.py` that the brief tests call (imported inside: react.py imports this module) ---

def react_with(ctx: Context, harness, log: Log, action: plan.Action) -> bool | None:
    from the_nod.driver import react
    return react.react_with(ctx, harness, log, action)


def react(ctx: Context, log: Log, action: plan.Action) -> bool | None:
    from the_nod.driver import react as module
    return module.react(ctx, log, action)


def ask_next_batch(ctx: Context, log: Log) -> str:
    from the_nod.driver import react
    return react.ask_next_batch(ctx, log)


def ask_pain(ctx: Context, log: Log) -> str:
    from the_nod.driver import react
    return react.ask_pain(ctx, log)
