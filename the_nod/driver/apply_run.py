"""The executor of a step run and of the acceptance: the agent command, the outcome, the state write.

The skeleton is the brief one (`apply_brief`): the lock, the command, a fresh context, the outcome write.
The driver never answers decisions and never restarts a stopped or hung run itself.
"""

import dataclasses
from pathlib import Path

from the_nod import harness as harness_mod
from the_nod import vocab
from the_nod.commands.card import load_card, make_return_decision
from the_nod.context import CliError, Context
from the_nod.driver import agent, apply_brief, files, lock, plan, results, usage
from the_nod.driver.log import Log
from the_nod.i18n import t
from the_nod.model import Card, Decision, Run
from the_nod.transitions import RunUsage, finish_run, make_acceptance, make_decision, start_run


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _stuck_minutes() -> str:
    """The "40 minutes" text from `plan.STUCK_SECONDS` at call time (the tests change it)."""
    return t("driver.minutes", n=int(plan.STUCK_SECONDS // 60))


def stuck_note() -> str:
    return t("driver.stuck_note", minutes=_stuck_minutes())


def stuck_reason() -> str:
    return t("driver.stuck_reason", minutes=_stuck_minutes())


def _reload_card(ctx: Context, log: Log, card_id: str, kind: str, result: Path) -> Card | None:
    try:
        return load_card(ctx, card_id)
    except (CliError, ValueError):
        if kind == "run":
            log.error(t("driver.card_gone_run", card=card_id, file=result))
        else:
            log.error(t("driver.card_gone_accept", card=card_id, file=result))
        return None


def _stuck_decision(ctx: Context, card: Card, reason: str) -> Decision:
    return make_decision(ctx.store, kind="run-stuck", question=t("driver.stuck_question", title=card.title),
                         proposed=vocab.RESTART, options=[vocab.RESTART, vocab.BACKLOG], reason=reason,
                         card=card.id, now=ctx.now)


# --- a step run ---

def run_step(ctx: Context, harness: harness_mod.Harness, log: Log, card_id: str, step: int) -> bool:
    """One run command of step `step`. `True` only if the run ended `ok`."""
    store = ctx.store
    card = apply_brief.load_card(ctx, log, card_id)
    if card is None:
        return False
    try:
        run, start = start_run(store, dataclasses.replace(card), step=step, contracts=0, now=ctx.now)
    except CliError as err:
        log.error(t("driver.run_not_started", card=card.id, error=err))
        return False
    try:
        command, prompt, values = apply_brief.render_command(ctx, harness, card, "run",
                                                             step=step, run=run.id)
    except harness_mod.HarnessError as err:
        return _unrunnable(ctx, log, card, str(err))
    if not lock.claim(ctx, f"driver run {card.id} {run.id} running", start):
        log.warn(apply_brief.lock_refused())
        return False
    result = apply_brief.launch(ctx, card, "run", prompt)
    log.info(t("driver.run_started", run=run.id, card=card.id, step=step))
    run_file = store.root / "runs" / f"{run.id}.md"
    outcome, changed = apply_brief.run_agent(ctx, log, command, prompt, values, kind="run",
                                             activity=lambda: _mtime(run_file))
    fresh = files.reopen(ctx)
    if not fresh.fresh:
        log.error(t("driver.run_stale", run=run.id, file=result))
        apply_brief.stale_restore(log, changed)
        return False
    return _finish_step(fresh, log, card.id, run.id, outcome, changed, result)


def _unrunnable(ctx: Context, log: Log, card: Card, reason: str) -> bool:
    """The run command cannot be built: the card is `returned` with the reason, no run, the queue goes on."""
    note = t("driver.run_unbuilt", reason=reason)
    back = dataclasses.replace(card, status="returned")
    decision = make_return_decision(ctx.store, back, note="", now=ctx.now, reason=note)

    def apply() -> None:
        ctx.store.save_card(back)
        ctx.store.save_decision(decision)

    if not ctx.write(f"driver run {card.id} returned", apply):
        log.warn(t("driver.run_return_local", card=card.id))
    log.error(t("driver.run_returned", card=card.id, note=note))
    return False


def _finish_step(ctx: Context, log: Log, card_id: str, run_id: str, outcome: agent.Outcome,
                 changed: list[str], result_file: Path) -> bool:
    card = _reload_card(ctx, log, card_id, "run", result_file)
    if card is None:
        return False
    try:
        run = ctx.store.load_run(run_id)
    except (FileNotFoundError, ValueError) as err:
        log.error(t("driver.run_unreadable", run=run_id, error=err, file=result_file))
        return False
    closed = card.status != "running" or run.finished is not None
    if apply_brief.unwritable(log, changed):
        return False
    hooks = apply_brief.tamper_text(ctx, changed) if changed else ""
    if hooks and closed:
        apply_brief.tampered(ctx, log, card, "run", changed)
        return False
    if closed:
        log.warn(t("driver.run_changed", run=run.id, status=card.status))
        return False
    spent = usage.measure(outcome.stdout, files.repo_root(ctx.store))
    if hooks:
        return _owner_stop(ctx, log, card, run, spent, note=t("driver.hooks_note"), text=hooks)
    if outcome.status == "stuck":
        return _returned(ctx, log, card, run, spent, stuck_note(),
                         _stuck_decision(ctx, card, stuck_reason()), outcome="stuck")
    res, error = apply_brief.read_result(results.read_run, result_file)
    wait = apply_brief.owner_wait(outcome, res.blocked if res else "")
    if wait:
        return _owner_stop(ctx, log, card, run, spent, note=t("driver.waits_owner_note", text=wait), text=wait)
    reason = apply_brief.outcome_failure(outcome) or error
    if not reason and res.result != "ok":
        reason = res.note or t("driver.stop_note")
    if reason:
        back = dataclasses.replace(card, status="returned")
        return _returned(ctx, log, card, run, spent, reason,
                         make_return_decision(ctx.store, back, note="", now=ctx.now, reason=reason),
                         outcome="stop")
    return _ok(ctx, log, card, run, spent, res)


def _usage(run: Run, spent: usage.Usage, contracts_done: int | None = None) -> RunUsage:
    done = run.contracts_done if contracts_done is None else contracts_done
    return RunUsage(contracts_done=done, tokens=spent.tokens, minutes=spent.minutes,
                    agents=spent.agents, tool_errors=spent.tool_errors)


def _ok(ctx: Context, log: Log, card: Card, run: Run, spent: usage.Usage,
        res: results.RunResult) -> bool:
    store = ctx.store
    done_run = dataclasses.replace(run, contracts_total=res.contracts_total or run.contracts_total)
    finish = finish_run(store, done_run, card, result="ok", usage=_usage(run, spent, res.contracts_done),
                        note=res.note, now=ctx.now)
    if not ctx.write(f"driver run {run.id} ok", finish):
        log.warn(t("driver.run_local", run=run.id))
    files.clear_attempt(store, card.id)
    log.info(t("driver.run_ok", run=run.id, card=card.id, status=card.status))
    return True


def _owner_stop(ctx: Context, log: Log, card: Card, run: Run, spent: usage.Usage, *,
                note: str, text: str) -> bool:
    """The run stops until an owner action: `stop` and `owner-action` in one commit, without `return`."""
    store = ctx.store
    finish = finish_run(store, run, card, result="stop", usage=_usage(run, spent), note=note, now=ctx.now)
    decision = apply_brief.make_owner_action(store, card, kind="run", text=text, now=ctx.now)

    def apply() -> None:
        finish()
        store.save_decision(decision)

    if not ctx.write(f"driver run {run.id} stop", apply):
        log.warn(t("driver.run_local", run=run.id))
    files.clear_attempt(store, card.id)
    log.warn(t("driver.waits_owner", kind=apply_brief.kind_name("run"), card=card.id, text=text))
    return False


def _returned(ctx: Context, log: Log, card: Card, run: Run | None, spent: usage.Usage,
              note: str, decision: Decision, *, outcome: str) -> bool:
    """`finish_run(stop)` (when there is a run), the card `returned` and the decision, in one commit."""
    store = ctx.store
    finish = (finish_run(store, run, card, result="stop", usage=_usage(run, spent), note=note, now=ctx.now)
              if run is not None else (lambda: None))
    back = dataclasses.replace(card, status="returned")

    def apply() -> None:
        finish()
        store.save_card(back)
        store.save_decision(decision)

    if run is None:
        summary, what = f"driver card {card.id} {outcome}", t("driver.card_running_no_run", card=card.id)
    else:
        summary, what = f"driver run {run.id} {outcome}", t("driver.run_of_card", run=run.id, card=card.id, note=note)
    if not ctx.write(summary, apply):
        log.warn(t("driver.written_local", summary=summary))
    log.error(t("driver.card_returned", what=what))
    return False


# --- a run without a live process ---

def stuck(ctx: Context, log: Log, card_id: str, run_id: str | None) -> bool:
    """A run hung without a live process (the driver restarted): `stop`, `returned`, `run-stuck`."""
    if not ctx.fresh:
        log.error(t("driver.stuck_stale", card=card_id))
        return False
    try:
        card = load_card(ctx, card_id)
        run = ctx.store.load_run(run_id) if run_id is not None else None
    except (CliError, FileNotFoundError, ValueError) as err:
        log.error(t("driver.stuck_not_written", card=card_id, error=err))
        return False
    if card.status != "running":
        log.warn(t("driver.stuck_wrong_status", card=card.id, status=card.status))
        return False
    if run is not None and (run.card != card.id or run.finished is not None):
        log.warn(t("driver.stuck_wrong_run", run=run.id, card=card.id))
        return False
    reason = stuck_reason() if run is not None else t("driver.no_run_reason")
    _returned(ctx, log, card, run, usage.Usage(), stuck_note(), _stuck_decision(ctx, card, reason),
              outcome="stuck")
    return True


# --- the acceptance ---

def accept(ctx: Context, harness: harness_mod.Harness, log: Log, card_id: str) -> bool:
    """One acceptance command. `True` means the acceptance from the agent result is written, the verdict waits for the owner."""
    card = apply_brief.load_card(ctx, log, card_id)
    if card is None:
        return False
    if card.status != "accepting":
        log.warn(t("driver.accept_wrong_status", card=card.id, status=card.status))
        return False
    try:
        command, prompt, values = apply_brief.render_command(ctx, harness, card, "accept")
    except harness_mod.HarnessError as err:
        reason = t("driver.accept_unbuilt", error=err)
        log.error(t("driver.accept_note", card=card.id, text=reason))
        return _unverified(ctx, log, card, reason)
    if not lock.claim(ctx, f"driver accept {card.id} accepting", lambda: None):
        log.warn(apply_brief.lock_refused())
        return False
    result = apply_brief.launch(ctx, card, "accept", prompt)
    log.info(t("driver.accept_started", card=card.id))
    outcome, changed = apply_brief.run_agent(ctx, log, command, prompt, values, kind="accept")
    fresh = files.reopen(ctx)
    if not fresh.fresh:
        log.error(t("driver.accept_stale", card=card.id, file=result))
        apply_brief.stale_restore(log, changed)
        return False
    done = _finish_accept(fresh, log, card.id, outcome, changed, result)
    apply_brief.record_usage(fresh, log, "accept", card.id, outcome, changed)
    return done


def _finish_accept(ctx: Context, log: Log, card_id: str, outcome: agent.Outcome,
                   changed: list[str], result_file: Path) -> bool:
    card = _reload_card(ctx, log, card_id, "accept", result_file)
    if card is None:
        return False
    if changed:
        apply_brief.tampered(ctx, log, card, "accept", changed)
        return False
    if card.status != "accepting":
        log.warn(t("driver.card_changed_accept", card=card.id, status=card.status))
        return False
    res, error = apply_brief.read_result(results.read_accept, result_file)
    wait = apply_brief.owner_wait(outcome, res.blocked if res else "")
    if wait:
        apply_brief.owner_action(ctx, log, card, kind="accept", text=wait)
        return False
    reason = apply_brief.outcome_failure(outcome) or error
    if not reason:
        try:
            made = make_acceptance(ctx.store, dataclasses.replace(card), level=res.level,
                                   result=res.result, evidence=res.evidence,
                                   frames=_frames(files.repo_root(ctx.store), res.frames),
                                   steps=res.steps, report=res.report, now=ctx.now)
            return _save_acceptance(ctx, log, card, made, ok=True)
        except CliError as err:
            reason = str(err)
    return _unverified(ctx, log, card, reason)


def _unverified(ctx: Context, log: Log, card: Card, reason: str) -> bool:
    """An `unverified` acceptance with the reason: the verdict still waits for the owner."""
    try:
        made = make_acceptance(ctx.store, dataclasses.replace(card), level=1, result=vocab.UNVERIFIED,
                               evidence=t("driver.accept_failed_evidence", reason=reason), frames=[], steps=[],
                               report=None, now=ctx.now)
    except CliError as err:
        log.error(t("driver.accept_not_written", card=card.id, reason=reason, error=err))
        return False
    return _save_acceptance(ctx, log, card, made, ok=False, reason=reason)


def _frames(root: Path, frames: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Frame paths from the repo root made absolute; a frame outside the repo is a `CliError`."""
    base = root.resolve()
    out = []
    for rel, caption in frames:
        path = (base / rel).resolve()
        if not path.is_relative_to(base):
            raise CliError(t("driver.frame_outside", path=rel))
        out.append((str(path), caption))
    return out


def _save_acceptance(ctx: Context, log: Log, card: Card, made, *, ok: bool, reason: str = "") -> bool:
    _, apply, warnings = made
    if not ctx.write(f"driver accept {card.id}", apply):
        log.warn(t("driver.accept_local", card=card.id))
    for warning in warnings:
        log.warn(t("driver.accept_note", card=card.id, text=warning))
    if ok:
        files.clear_attempt(ctx.store, card.id)
        log.info(t("driver.accept_done", card=card.id))
    else:
        log.error(t("driver.accept_failed", card=card.id, reason=reason))
    return ok
