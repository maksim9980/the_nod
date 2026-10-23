"""`nod migrate`: the state of the older version, `.sprintboot/`, becomes `.nod/`."""

import argparse
import sys
from pathlib import Path

from the_nod import context, migrate, snapshot
from the_nod.i18n import t
from the_nod.migrate import LocalFiles, MigrationPlan
from the_nod.paths import STATE_DIR_NAME, NotARepo, main_worktree_root

SHORT_SHA = 7
FOLDERS = {"old": f"{migrate.LEGACY_DIR}/", "new": f"{STATE_DIR_NAME}/"}


def add_parser(sub) -> None:
    parser = sub.add_parser("migrate", help=t("migrate.help"))
    parser.add_argument("--dry-run", action="store_true", help=t("migrate.help_dry_run"))
    parser.set_defaults(run=run)


def _repo(root: str | None) -> Path:
    """The root of the repo's main worktree from `--root` or cwd; outside git, that folder itself."""
    given = Path(root).absolute() if root is not None else Path.cwd()
    if given.name in (migrate.LEGACY_DIR, STATE_DIR_NAME):
        given = given.parent
    try:
        return main_worktree_root(given)
    except NotARepo:
        return given


def _local_lines(local: LocalFiles, dry_run: bool) -> list[str]:
    count = len(local.moves) + len(local.merged) + len(local.dropped)
    lines = [t("migrate.local_move" if dry_run else "migrate.local_moved", count=count, **FOLDERS)]
    if dry_run:
        lines += [f"  {rel}" for rel in local.moves]
    lines += [t("migrate.local_merged", path=rel, **FOLDERS) for rel, _ in local.merged]
    return lines + [t("migrate.local_dropped", path=rel) for rel in local.dropped]


def _lines(plan: MigrationPlan, dry_run: bool, pulled: bool) -> list[str]:
    """The changes, one per line; a dry run also lists the files with older values."""
    if plan.local is not None:
        return _local_lines(plan.local, dry_run)
    lines = [t("migrate.pull_plan")] if dry_run and plan.pulls else []
    if pulled:
        lines.append(t("migrate.pulled"))
    lines.append(t("migrate.move" if dry_run else "migrate.moved", **FOLDERS))
    if plan.rewrites:
        lines.append(t("migrate.rewrite", count=len(plan.rewrites)))
        if dry_run:
            lines += [f"  {rewrite.path}" for rewrite in plan.rewrites]
    manifest = plan.manifest
    if manifest.needs_renamed:
        lines.append(t("migrate.needs"))
    if manifest.lang_added:
        lines.append(t("migrate.lang_added", lang=migrate.LEGACY_LANG))
    if manifest.git_added:
        lines.append(t("migrate.git_added"))
    if plan.gitignore_lines:
        lines.append(t("migrate.gitignore", count=plan.gitignore_lines))
    if dry_run and plan.git:
        lines.append(t("migrate.commit_plan", subject=migrate.SUBJECT))
    if dry_run and plan.git and plan.origin and manifest.push:
        lines.append(t("migrate.push_plan"))
    return lines


def _warnings(plan: MigrationPlan) -> list[str]:
    """What the owner checks by hand: the adapter replaced, manifest lines with the older name, files left."""
    adapter = plan.manifest.adapter
    found = [] if adapter is None else [t("migrate.adapter", adapter=adapter)]
    found += [t("migrate.old_name", line=n, text=text) for n, text in plan.manifest.old_names]
    kept = plan.local.kept if plan.local is not None else ()
    return found + [t("migrate.local_kept", path=rel, **FOLDERS) for rel in kept]


def _data(plan: MigrationPlan, dry_run: bool, pulled: bool, sha: str | None, warnings: list[str]) -> dict:
    manifest, local = plan.manifest, plan.local
    return {"dry_run": dry_run, "from": migrate.LEGACY_DIR, "to": STATE_DIR_NAME, "pulled": pulled,
            "rewritten": [rewrite.path for rewrite in plan.rewrites],
            "manifest": {"adapter": manifest.adapter, "needs_renamed": manifest.needs_renamed,
                         "lang_added": manifest.lang_added, "git_added": manifest.git_added},
            "gitignore_lines": plan.gitignore_lines, "warnings": warnings, "commit": sha,
            "push": plan.git and plan.origin and manifest.push,
            "local": None if local is None else {
                "moved": list(local.moves), "merged": [rel for rel, _ in local.merged],
                "dropped": list(local.dropped), "kept": list(local.kept)}}


def _snapshot(state_dir: Path) -> None:
    """A fresh state.json, as after every write: the pane finds the state by it and reads the new values."""
    ctx = context.open(argparse.Namespace(root=str(state_dir)), sync=False)
    state = snapshot.build(ctx.store, now=ctx.now, host=ctx.host, since=None, fresh=ctx.fresh,
                           stale_since=ctx.stale_since)
    snapshot.write(ctx.store, state)


def _pulled(repo: Path, plan: MigrationPlan) -> MigrationPlan:
    """The plan after `pull --ff-only`; a pull that does not go through refuses like a stale state."""
    try:
        return migrate.pull(repo, plan)
    except migrate.PullFailed as error:
        raise context.Stale(str(error)) from error


def _done_line(plan: MigrationPlan, sha: str | None) -> str | None:
    if plan.local is not None:
        return t("migrate.local_no_commit")
    if not plan.git:
        return None
    return t("migrate.nothing_to_commit") if sha is None else t(
        "migrate.committed", sha=sha[:SHORT_SHA], subject=migrate.SUBJECT)


def run(args) -> int:
    context.refuse_agent()
    repo = _repo(args.root)
    plan = migrate.plan(repo)
    pulled = not args.dry_run and plan.pulls  # a dry run touches neither the network nor the files
    if pulled:
        plan = _pulled(repo, plan)
    warnings = _warnings(plan)
    for line in warnings:
        print(line, file=sys.stderr)
    lines = _lines(plan, args.dry_run, pulled)
    if args.dry_run:
        context.emit(args, _data(plan, True, False, None, warnings),
                     "\n".join([t("migrate.dry_run"), *(f"  {line}" for line in lines)]))
        return 0
    sha = migrate.apply(repo, plan)
    done = _done_line(plan, sha)
    context.emit(args, _data(plan, False, pulled, sha, warnings), "\n".join([*lines, *([done] if done else [])]))
    _snapshot(repo / STATE_DIR_NAME)
    return 0
