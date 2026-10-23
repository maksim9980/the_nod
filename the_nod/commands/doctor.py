"""`nod doctor`: checks the machine against the `[needs]` table of the manifest; writes nothing."""

from dataclasses import asdict

from the_nod import context, harness
from the_nod.context import CliError
from the_nod.i18n import t
from the_nod.portability import doctor

EXIT_MISSING = 1


def add_parser(sub) -> None:
    parser = sub.add_parser("doctor", help=t("help.doctor"))
    parser.set_defaults(run=run)


def run(args) -> int:
    ctx = context.open(args, sync=False)  # no pull: doctor works offline too
    try:
        needs = harness.load(ctx.store).needs
    except harness.HarnessError as err:
        raise CliError(str(err)) from err
    result = doctor.checks(ctx.store, needs, doctor.machine())
    ok = doctor.all_ok(result)
    context.emit(args, {"ok": ok, "checks": [asdict(check) for check in result]}, doctor.table(result))
    return 0 if ok else EXIT_MISSING
