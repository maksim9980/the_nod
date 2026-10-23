"""`nod driver`: one pass (`once`), a loop by default, the autostart at login (`install`/`uninstall`)."""

from pathlib import Path

from the_nod import context, harness
from the_nod.driver import autostart, loop, once, signals
from the_nod.driver.log import Log
from the_nod.i18n import t

EXIT_REFUSED = 3
AUTOSTART_ACTIONS = ("install", "uninstall")  # the only actions with a `--dry-run`


def add_parser(sub) -> None:
    parser = sub.add_parser("driver", help=t("help.driver"))
    parser.add_argument("action", nargs="?", choices=("once", "install", "uninstall"),
                        help=t("help.driver_action"))
    parser.add_argument("--interval", type=float, default=30.0, help=t("help.driver_interval"))
    parser.add_argument("--passes", type=int, default=0, help=t("help.driver_passes"))
    parser.add_argument("--dry-run", action="store_true", help=t("help.driver_dry_run"))
    parser.set_defaults(run=run)


def _once(args) -> int:
    root = context.resolve_state_dir(args.root, Path.cwd())
    log = Log(root / "driver.log", echo=False)
    try:
        result = once.run_pass(args, log=log)
    except harness.HarnessError as err:
        raise context.CliError(str(err)) from err
    print(f"{result.did}: {result.message}")
    return EXIT_REFUSED if result.did == "stale" else 0


def run(args) -> int:
    context.refuse_agent()  # the agent neither starts nested passes nor sets up autostart
    if args.dry_run and args.action not in AUTOSTART_ACTIONS:
        # A pass has no preview: without this refusal `once --dry-run` runs the agent and spends money.
        raise context.CliError(t("driver.dry_run_autostart_only"))
    if args.action == "once":
        with signals.exit_on_signals():  # a SIGTERM to the driver does not leave the agent running
            return _once(args)
    if args.action is None:
        with signals.exit_on_signals():
            return loop.run_loop(args, interval=args.interval, passes=args.passes)
    state_dir = context.resolve_state_dir(args.root, Path.cwd())
    context.use_lang(state_dir)
    root = state_dir.parent
    action = autostart.install if args.action == "install" else autostart.uninstall
    return action(root, dry_run=args.dry_run)
