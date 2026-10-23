"""`nod install`: steps from the failed doctor checks, their execution and the report lines."""
import contextlib
import io
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from the_nod.context import CliError
from the_nod.driver import autostart
from the_nod.i18n import t
from the_nod.portability import doctor
from the_nod.portability.doctor import Check, Machine
from the_nod.portability.needs import COPY_KINDS, Needs
from the_nod.store import Store


@dataclass(frozen=True)
class Step:
    kind: str
    what: str
    run: Callable[[], str] | None


def _source_in_target(src: Path, dst: Path) -> bool:
    """Every file of the source folder is in the target with the same bytes; extras in the target do not count."""
    for path in src.rglob("*"):
        if path.is_file():
            target = dst / path.relative_to(src)
            if not target.is_file() or target.read_bytes() != path.read_bytes():
                return False
    return True


def copy_needed(src: Path, dst: Path, *, dry_run: bool) -> str:
    """Copies a file or folder from the repo into `~/.claude` if the content differs; deletes nothing in `~/.claude`."""
    if doctor.same_content(src, dst):
        return t("install.already")
    extra = doctor.extra_files(src, dst)
    if extra and _source_in_target(src, dst):
        return t("install.extra_left", path=dst, files=", ".join(extra))
    if dry_run:
        return t("install.would_copy", path=dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    if extra:
        return t("install.copied_extra", path=dst, files=", ".join(extra))
    return t("install.copied", path=dst)


def _job(repo_root: Path, *, dry_run: bool) -> Callable[[], str]:
    def run() -> str:
        """The autostart output goes into the step result, not to stdout: stdout would break `--json`."""
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = autostart.install(repo_root, dry_run=dry_run)
        if code != 0:
            raise CliError(t("install.job_failed", code=code))
        text = captured.getvalue().strip()
        return t("install.done_with", text=text) if text else t("install.done")
    return run


def _copy_sources(needs: Needs) -> dict[str, tuple[str, str]]:
    """The copy check name `<kind>/<name>` to (kind, path in the repo)."""
    return {f"{kind}/{Path(path).name}": (kind, path) for kind in COPY_KINDS for path in getattr(needs, kind)}


def _copy_step(check: Check, sources: dict[str, tuple[str, str]], m: Machine, repo_root: Path,
               *, dry_run: bool) -> Step:
    """The target is only `<Claude folder>/<kind>/<name>`: the raw path from the manifest never becomes a target."""
    kind, path = sources[check.name]
    src = repo_root / path
    dst = doctor.config_dir(m) / kind / Path(path).name
    return Step("copy", f"{check.name} → {dst}", lambda: copy_needed(src, dst, dry_run=dry_run))


def plan(checks: list[Check], *, needs: Needs, m: Machine, store: Store,
         dry_run: bool) -> list[Step]:
    """Steps for the failed checks: copies, the job, then the manual ones."""
    failed = [check for check in checks if not check.ok]
    autos = {check.auto for check in failed}
    repo_root = store.root.parent
    steps = []
    sources = _copy_sources(needs)
    steps += [_copy_step(check, sources, m, repo_root, dry_run=dry_run) for check in failed if check.auto == "copy"]
    if "job" in autos:
        steps.append(Step("job", t("install.job_step"), _job(repo_root, dry_run=dry_run)))
    steps += [Step("manual", f"{check.name}: {check.fix}", None) for check in failed if check.auto is None]
    return steps


def apply(steps: list[Step], *, dry_run: bool) -> list[str]:
    """Runs the steps in order; with `dry_run` nothing runs, the steps are only named."""
    lines = []
    for step in steps:
        if step.run is None:
            lines.append(t("install.line_manual", what=step.what))
        elif dry_run:
            lines.append(t("install.line_dry", what=step.what))
        else:
            lines.append(f"{step.kind}: {step.what} — {step.run()}")
    return lines
