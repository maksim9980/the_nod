"""English messages of `nod driver install|uninstall`: the driver autostart at login.

Literal braces are doubled: every message goes through `str.format`.
"""

MESSAGES = {
    # dry runs
    "autostart.would_write": "would write {path}:",
    "autostart.would_run": "would run:",
    "autostart.would_remove": "would remove {path}",
    "autostart.with_systemd": "with systemd --user:",
    "autostart.without_systemd": "without systemd --user, this crontab line instead "
                                 "(replacing the lines ending with {tag}):",
    "autostart.would_drop_cron": "would drop the crontab lines ending with {tag}",

    # real runs
    "autostart.wrote": "wrote {path}",
    "autostart.removed": "removed {path}",
    "autostart.cron_set": "crontab line set: {line}",
    "autostart.cron_dropped": "crontab lines ending with {tag} dropped",
    "autostart.cron_path_cut": "a crontab line takes at most {limit} bytes: PATH is cut from {total} to {kept} directories",
    "autostart.cron_path_gone": "a crontab line takes at most {limit} bytes and none of the {total} PATH directories fits: "
                                "the job gets the default PATH of cron",
    "autostart.cron_claude_dropped": "{folder} holds claude and had to be cut from PATH: "
                                     "the job started by cron will not find claude",

    # refusals
    "autostart.tr_too_long": "the task command is {length} characters, schtasks takes at most {limit}: "
                             "move the repo to a shorter path, or install Nod with pip into a short path",
    "autostart.unit_failed": "{command} returned code {code}: {path} removed, the job is not set up",
    "autostart.disable_failed": "{command} returned code {code}: {path} kept",
    "autostart.run_failed": "could not run {program}: {error}",
}
