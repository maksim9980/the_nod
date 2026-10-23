"""One driver pass: the reactions to answers, then at most one agent command.

A pass does not fall: an action error goes to the log and to the `error` result. The pid file is always removed.
"""

import time
from dataclasses import dataclass

from the_nod import context, harness as harness_mod
from the_nod.context import CliError, Context, Stale
from the_nod.driver import apply_brief, apply_run, files, lock, plan, react
from the_nod.driver.log import Log
from the_nod.driver.results import ResultError
from the_nod.gitsync import GitError, ProtectedBranch
from the_nod.i18n import t
from the_nod.store import LoadError

MAX_REACTIONS = 20
# After the pid file is taken, a pass does not fall: a broken state (`LoadError`, `ValueError`) is an `error` too.
ACTION_ERRORS = (CliError, ResultError, harness_mod.HarnessError, OSError, Stale, ProtectedBranch, GitError,
                 LoadError, ValueError)


class OtherHost(CliError):
    """The manifest names another machine as the driver host: a pass refuses, and the loop stops."""


@dataclass(frozen=True)
class PassResult:
    """The pass result: `did` is what was done, `message` is a line for a human."""

    did: str
    message: str


def _stale(ctx: Context) -> PassResult:
    return PassResult("stale", t("driver.stale", since=ctx.stale_since))


def _busy(pid: int) -> PassResult:
    return PassResult("busy", t("driver.busy") if pid == -1 else t("driver.busy_pid", pid=pid))


def _refused() -> PassResult | None:
    return PassResult("lock-lost", lock.last_refusal) if lock.last_refusal else None


def _react_all(ctx: Context, log: Log) -> PassResult | None:
    """Reactions one by one, the state is read again after each; a result when the pass ends there."""
    tried: set[str] = set()
    for _ in range(MAX_REACTIONS):
        store = ctx.store
        pending = [a for a in plan.reactions(store.cards(), store.decisions()) if a.decision not in tried]
        if not pending:
            return None
        action = pending[0]
        tried.add(action.decision)
        lock.last_refusal = ""
        rebriefed = react.react(ctx, log, action)
        if rebriefed is True:
            return PassResult("react", t("driver.rebrief", card=action.card))
        if rebriefed is False:
            return _refused() or PassResult("react", t("driver.failed", action=f"react {action.card}"))
    log.warn(t("driver.too_many_reactions", limit=MAX_REACTIONS))
    return None


def _run_mtime(ctx: Context):
    runs = ctx.store.root / "runs"

    def mtime(run_id: str) -> float:
        try:
            return (runs / f"{run_id}.md").stat().st_mtime
        except OSError:
            return 0.0

    return mtime


def _asked(kind: str, decision_id: str) -> PassResult:
    return PassResult(kind, f"{kind} {decision_id}") if decision_id else PassResult("idle", t("driver.nothing_to_do"))


def _act(ctx: Context, harness: harness_mod.Harness, log: Log) -> PassResult:
    store = ctx.store
    action = plan.next_action(store.cards(), store.decisions(), store.runs(), store.order(), ctx.now,
                              run_mtime=_run_mtime(ctx), clock=time.time())
    kind, card = action.kind, action.card
    if kind == "next-batch":
        return _asked(kind, react.ask_next_batch(ctx, log))
    if kind == "pain":
        return _asked(kind, react.ask_pain(ctx, log))
    lock.last_refusal = ""
    if kind == "brief":
        done = apply_brief.brief(ctx, harness, log, card)
    elif kind == "run":
        done = apply_run.run_step(ctx, harness, log, card, action.step)
    elif kind == "accept":
        done = apply_run.accept(ctx, harness, log, card)
    elif kind == "stuck":
        done = apply_run.stuck(ctx, log, card, action.run)
    else:
        return PassResult("idle", t("driver.nothing_to_do"))
    if done:
        return PassResult(kind, f"{kind} {card}")
    if kind != "stuck":
        refused = _refused()
        if refused is not None:
            return refused
    return PassResult(kind, t("driver.failed", action=f"{kind} {card}"))


def _locked_pass(ctx: Context, harness: harness_mod.Harness, log: Log) -> PassResult:
    try:
        held = ctx.store.lock()
        if lock.lock_state(held, ctx.host, ctx.now) == "foreign":
            return PassResult("foreign", lock.foreign_message(held))
        # Reactions write before `claim`, and `ctx.write` commits `add -A .nod`: a dirty tree means no write at all.
        dirty = ctx.sync.dirty() if ctx.sync is not None else []
        if dirty:
            return PassResult("lock-lost", t("driver.dirty_tree", paths=", ".join(dirty)))
        ended = _react_all(ctx, log)
        if ended is not None:
            return ended
        ctx = files.reopen(ctx)
        if not ctx.fresh:
            return _stale(ctx)
        return _act(ctx, harness, log)
    except ACTION_ERRORS as err:
        log.error(t("driver.pass_aborted", error=err))
        return PassResult("error", str(err))


def run_pass(args, *, log: Log) -> PassResult:
    """One pass. A `CliError` or `HarnessError` before the lock (the manifest, another host) goes up."""
    ctx = context.open(args)
    if not ctx.fresh:
        return _stale(ctx)
    store = ctx.store
    harness = harness_mod.load(store)
    if harness.driver_host and harness.driver_host != ctx.host:
        raise OtherHost(t("driver.other_host", host=harness.driver_host))
    other = lock.process_lock(store)
    if other is not None:
        return _busy(other)
    try:
        return _locked_pass(ctx, harness, log)
    finally:
        lock.release(store)
