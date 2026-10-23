"""State transitions without argparse: shared by the `nod` commands and the driver.

Each function checks and prepares the new state; the caller writes it through
`Context.write`, so the functions that change files return `apply`.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from the_nod import vocab
from the_nod.context import CliError
from the_nod.i18n import t
from the_nod.model import (ACCEPT_LEVELS, ACCEPT_RESULTS, DECISION_KINDS,
                           Acceptance, Card, Decision, Frame, Run)
from the_nod.store import FRAME_EXTENSIONS

RESULTS = ("ok", "stop")
NO_RUN_STATUSES = ("done", "waiting-verdict")
MAX_FRAMES = 6


@dataclass(frozen=True)
class RunUsage:
    contracts_done: int = 0
    tokens: int = 0
    minutes: int = 0
    agents: int = 0
    tool_errors: int = 0


def check_result(result: str) -> None:
    if result not in RESULTS:
        raise CliError(t("transitions.bad_result", result=result, allowed=", ".join(RESULTS)))


def open_run(store, card_id: str) -> Run | None:
    """The run of the card that has not finished, if any."""
    return next((r for r in store.runs() if r.card == card_id and r.finished is None), None)


def _append_line(body: str, line: str) -> str:
    return f"{body}\n{line}" if body else line


def _end_run(run: Run, result: str, note: str, now: str) -> None:
    """The run ends: the time, the result and the note; its usage and its card stay as they are."""
    run.finished, run.result = now, result
    if note:
        run.body = _append_line(run.body, note)


def stop_run(store, run: Run, *, note: str, now: str) -> Callable[[], None]:
    """End an open run with `stop`. `apply` writes only the run: the caller sets the card and writes it."""
    if run.finished is not None:
        raise CliError(t("transitions.run_finished", finished=run.finished))
    _end_run(run, "stop", note, now)

    def apply() -> None:
        store.save_run(run)

    return apply


def start_run(store, card: Card, *, step: int | None, contracts: int,
              now: str) -> tuple[Run, Callable[[], None]]:
    if card.status in NO_RUN_STATUSES:
        raise CliError(t("transitions.no_run", card=card.id, status=card.status))
    open_one = open_run(store, card.id)
    if open_one and card.status == "running":
        raise CliError(t("transitions.run_open", run=open_one.id))
    if step is not None and step not in [s.n for s in card.steps]:
        raise CliError(t("transitions.no_step", step=step))
    run = Run(id=store.new_id("r"), card=card.id, started=now, step=step, contracts_total=contracts)
    # An open run of a card that is not running was abandoned (an old state: `card return` left it open).
    # It would block the card for good, so it ends with `stop` in the commit that starts the new run.
    close_old = (stop_run(store, open_one, note=t("transitions.run_abandoned", run=run.id), now=now)
                 if open_one else None)
    card.status = "running"

    def apply() -> None:
        if close_old is not None:
            close_old()
        store.save_run(run)
        store.save_card(card)

    return run, apply


def progress_run(store, run: Run, *, contracts_done: int, now: str) -> Callable[[], None]:
    if run.finished is not None:
        raise CliError(t("transitions.run_finished", finished=run.finished))
    run.contracts_done = contracts_done
    run.body = _append_line(run.body, t("transitions.progress_line", now=now, done=contracts_done))

    def apply() -> None:
        store.save_run(run)

    return apply


def finish_run(store, run: Run, card: Card, *, result: str, usage: RunUsage,
               note: str, now: str) -> Callable[[], None]:
    check_result(result)
    if run.finished is not None:
        raise CliError(t("transitions.run_finished", finished=run.finished))
    _end_run(run, result, note, now)
    run.contracts_done, run.tokens, run.minutes = usage.contracts_done, usage.tokens, usage.minutes
    run.agents, run.tool_errors = usage.agents, usage.tool_errors
    if result == "ok":
        for step in card.steps:
            if step.n == run.step:
                step.done = True
    all_done = all(s.done for s in card.steps)
    card.status = "accepting" if result == "ok" and all_done else "ready"

    def apply() -> None:
        store.save_run(run)
        store.save_card(card)

    return apply


def _check_frames(result: str, level: int, frames: list[tuple[str | None, str | None]]) -> list[Path]:
    """Checks in the order of `nod accept`; `None` in a pair means no frame or no caption."""
    if result not in ACCEPT_RESULTS:
        raise CliError(t("transitions.bad_result", result=result, allowed=", ".join(ACCEPT_RESULTS)))
    if level not in ACCEPT_LEVELS:
        raise CliError(t("transitions.bad_level", level=level))
    if len(frames) > MAX_FRAMES:
        raise CliError(t("transitions.too_many_frames", count=len(frames)))
    if any(path is None or caption is None for path, caption in frames):
        raise CliError(t("transitions.captions_mismatch"))
    paths = [Path(path) for path, _ in frames]
    for path in paths:
        if not path.is_file():
            raise CliError(t("transitions.no_frame", path=path))
        if path.suffix.lower() not in FRAME_EXTENSIONS:
            raise CliError(t("store.bad_frame_ext", ext=path.suffix))
    return paths


def make_acceptance(store, card: Card, *, level: int, result: str, evidence: str,
                    frames: list[tuple[str | None, str | None]], steps: list[str], report: str | None,
                    now: str) -> tuple[Decision, Callable[[], None], list[str]]:
    """The verdict for the owner, `apply`, and the warnings (filled by `apply`)."""
    if card.status == "done":
        raise CliError(t("card.closed", card=card.id))
    paths = _check_frames(result, level, frames)
    waiting = next((d for d in store.decisions()
                    if d.kind == "verdict" and d.card == card.id and d.answer is None), None)
    if waiting:
        raise CliError(t("transitions.verdict_waiting", decision=waiting.id))
    reason = f"{result}; {evidence}" if evidence else result
    verdict = Decision(id=store.new_id("d"), kind="verdict", created=now,
                       question=t("transitions.verdict_question", title=card.title), proposed=vocab.ACCEPT,
                       options=[vocab.ACCEPT, vocab.RETURN], reason=reason, card=card.id)
    card.status = "waiting-verdict"
    warnings: list[str] = []

    def apply() -> None:
        saved = []
        for n, (path, (_, caption)) in enumerate(zip(paths, frames), start=1):
            name = store.add_frame(card.id, path, n)
            if name is None:
                warnings.append(t("transitions.frame_too_big", path=path))
            saved.append(Frame(path=name or str(path), caption=caption))
        store.save_acceptance(Acceptance(
            card=card.id, level=level, result=result, created=now, evidence=evidence,
            frames=saved, steps=steps, report=report))
        store.save_decision(verdict)
        store.save_card(card)

    return verdict, apply, warnings


def make_decision(store, *, kind: str, question: str, proposed: str, options: list[str],
                  reason: str = "", card: str | None = None, body: str = "",
                  now: str) -> Decision:
    if kind not in DECISION_KINDS:
        raise CliError(t("decision.bad_kind", kind=kind, allowed=", ".join(DECISION_KINDS)))
    return Decision(id=store.new_id("d"), kind=kind, created=now, question=question,
                    proposed=proposed, options=options, reason=reason, card=card, body=body)
