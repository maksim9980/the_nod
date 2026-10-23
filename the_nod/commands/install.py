"""`nod install`: brings the machine up to the `[needs]` table — copies into ~/.claude and the driver task."""

from dataclasses import asdict

from the_nod import context, harness
from the_nod.context import CliError
from the_nod.i18n import t
from the_nod.portability import doctor
from the_nod.portability import install as portability_install

EXIT_MISSING = 1


def add_parser(sub) -> None:
    parser = sub.add_parser("install", help=t("help.install"))
    parser.add_argument("--dry-run", action="store_true", help=t("help.install_dry_run"))
    parser.set_defaults(run=run)


def run(args) -> int:
    context.refuse_agent()  # the agent neither registers login jobs nor copies files into ~/.claude
    ctx = context.open(args, sync=False)  # no pull: install works offline too
    try:
        needs = harness.load(ctx.store).needs
    except harness.HarnessError as err:
        raise CliError(str(err)) from err
    m = doctor.machine()
    before = doctor.checks(ctx.store, needs, m)
    steps = portability_install.plan(before, needs=needs, m=m, store=ctx.store, dry_run=args.dry_run)
    done = portability_install.apply(steps, dry_run=args.dry_run) if steps else [t("install.nothing")]
    after = before if args.dry_run else doctor.checks(ctx.store, needs, m)
    if args.dry_run:
        ok = not any(step.kind == "manual" for step in steps)
    else:
        ok = doctor.all_ok(after)
    context.emit(args, {"done": done, "ok": ok, "checks": [asdict(check) for check in after]},
                 "\n".join(done) + "\n" + doctor.table(after))
    return 0 if ok else EXIT_MISSING
