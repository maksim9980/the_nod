"""Driver autostart: Task Scheduler, a LaunchAgent, systemd --user and the crontab fallback.

Nothing here touches the machine: every test injects a `Target` and a fake `run`.
"""
import dataclasses
import hashlib
import json
import os
import plistlib
import re
import shlex
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from xml.sax.saxutils import escape

import pytest

from the_nod import i18n
from the_nod.cli import main
from the_nod.context import CliError
from the_nod.driver import autostart, signals
from the_nod.driver.autostart import JobStatus, Target, job_argv, job_suffix, linux, macos, windows
from the_nod.portability import doctor
from the_nod.portability.doctor import Machine
from tests.driver_helpers import driver_run, setup

CYRILLIC = re.compile(r"[Ѐ-ӿ]")
SPACED = Path("/Users/Jane Doe/Library/Application Support/Claude/plugins/nod/the_nod/__main__.py")
OLD_CORE = Path("/Users/Jane Doe/old/nod/the_nod/__main__.py")
WIN_PYTHON = "C:/Users/Jane Doe/AppData/Local/Programs/Python/Python313/pythonw.exe"
WIN_CORE = Path("C:/Users/Jane Doe/AppData/Roaming/nod/the_nod/__main__.py")
WIN_REPO = Path("C:/Users/Jane Doe/Tidepool")
POSIX_PYTHON = "/usr/bin/python3"
MAC_REPO = Path("/Users/Jane Doe/Tidepool")
LINUX_REPO = Path("/home/Jane Doe/Tidepool")


class FakeRun:
    """A `subprocess.run` stand-in: records each call, keeps a crontab as bytes, answers the systemd probe.

    `fails` maps the start of a command line to the (code, stderr) it answers with.
    """

    def __init__(self, *, systemd: bool = True, crontab: str | bytes | None = None, code: int = 0, stdout: str = "",
                 query: str | None = None, fails: dict[str, tuple[int, str]] | None = None):
        self.calls: list[tuple[list[str], dict]] = []
        self.systemd = systemd
        self.raw = crontab.encode("utf-8", "surrogateescape") if isinstance(crontab, str) else crontab
        self.code = code
        self.stdout = stdout
        self.query = query
        self.fails = fails or {}

    @property
    def argvs(self) -> list[list[str]]:
        return [argv for argv, _ in self.calls]

    @property
    def crontab(self) -> str | None:
        return None if self.raw is None else self.raw.decode("utf-8", "surrogateescape")

    def __call__(self, argv, **kwargs):
        argv = list(argv)
        self.calls.append((argv, kwargs))
        line = " ".join(argv)
        for start, (code, stderr) in self.fails.items():
            if line.startswith(start):
                return SimpleNamespace(returncode=code, stdout="", stderr=stderr)
        if argv[:3] == ["systemctl", "--user", "show-environment"]:
            return self._done(0 if self.systemd else 1)
        if argv[0] == "crontab":
            assert "text" not in kwargs and "encoding" not in kwargs, "crontab is read and written as bytes"
            if argv == ["crontab", "-"]:
                self.raw = kwargs["input"]
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
            if self.raw is None:
                return SimpleNamespace(returncode=1, stdout=b"", stderr=b"no crontab for jane")
            return SimpleNamespace(returncode=0, stdout=self.raw, stderr=b"")
        if argv[:2] == ["schtasks", "/Query"]:
            return self._done(1, "") if self.query is None else self._done(0, self.query)
        return self._done(self.code, self.stdout)

    @staticmethod
    def _done(code: int, stdout: str = "") -> SimpleNamespace:
        return SimpleNamespace(returncode=code, stdout=stdout, stderr="")


def win(core: Path = WIN_CORE, python: str = WIN_PYTHON) -> Target:
    return Target(platform="win32", home=Path("C:/Users/Jane Doe"), python=python, core=core, uid=None, env={})


def mac(home: Path, core: Path = SPACED, env: dict | None = None) -> Target:
    return Target(platform="darwin", home=home, python=POSIX_PYTHON, core=core, uid=501, env=env or {})


def lin(home: Path, core: Path = SPACED, env: dict | None = None) -> Target:
    return Target(platform="linux", home=home, python=POSIX_PYTHON, core=core, uid=1000, env=env or {})


def plist_in(text: str) -> dict:
    """The plist printed by a dry run, parsed back."""
    start, end = text.index("<?xml"), text.index("</plist>") + len("</plist>")
    return plistlib.loads(text[start:end].encode("utf-8"))


def task_xml(target: Target, repo: Path) -> str:
    """What `schtasks /Query /XML` gives for our task: the program in <Command>, the rest in <Arguments>."""
    line = subprocess.list2cmdline(job_argv(target, repo))
    split = line.index('"', 1) + 1 if line.startswith('"') else line.index(" ")
    command, arguments = line[:split], line[split:].strip()
    return ('<?xml version="1.0" encoding="UTF-16"?>\n'
            '<Task version="1.6" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
            '  <Actions Context="Author">\n    <Exec>\n'
            f'      <Command>{escape(command)}</Command>\n'
            f'      <Arguments>{escape(arguments)}</Arguments>\n'
            '    </Exec>\n  </Actions>\n</Task>\n')


# --- names and the shared pieces ---

def test_job_suffix_and_argv(tmp_path):
    repo = tmp_path / "Tidepool"
    expected = hashlib.sha256(str(repo.resolve()).encode("utf-8")).hexdigest()[:8]
    assert job_suffix(repo) == expected and re.fullmatch(r"[0-9a-f]{8}", expected)
    assert job_suffix(tmp_path / "Other") != expected
    target = mac(tmp_path)
    assert job_argv(target, repo) == [POSIX_PYTHON, "-P", str(SPACED), "--root", str(repo), "driver"]


def test_names_on_each_platform(tmp_path):
    suffix = job_suffix(WIN_REPO)
    assert windows.task_name(WIN_REPO) == f"Nod driver Tidepool {suffix}"
    assert macos.label(MAC_REPO) == f"the-nod.driver.{job_suffix(MAC_REPO)}"
    assert macos.plist_path(mac(tmp_path), MAC_REPO) == (
        tmp_path / "Library" / "LaunchAgents" / f"the-nod.driver.{job_suffix(MAC_REPO)}.plist")
    assert linux.unit_name(LINUX_REPO) == f"nod-driver-{job_suffix(LINUX_REPO)}.service"
    assert linux.unit_dir(lin(tmp_path)) == tmp_path / ".config" / "systemd" / "user"
    xdg = tmp_path / "xdg"
    assert linux.unit_dir(lin(tmp_path, env={"XDG_CONFIG_HOME": str(xdg)})) == xdg / "systemd" / "user"
    assert linux.unit_dir(lin(tmp_path, env={"XDG_CONFIG_HOME": ""})) == tmp_path / ".config" / "systemd" / "user"


def test_core_main_is_package_entry():
    core = autostart.core_main()
    assert core.name == "__main__.py" and core.parent.name == "the_nod" and core.is_absolute() and core.is_file()


def test_current_target_describes_this_machine():
    target = autostart.current_target()
    assert target.platform == sys.platform and target.home == Path.home() and target.core == autostart.core_main()
    if sys.platform == "win32":
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        assert target.python == (str(pythonw) if pythonw.exists() else sys.executable) and target.uid is None
    else:
        assert target.python == sys.executable and target.uid == os.getuid()
    assert target.env.get("PATH") == os.environ.get("PATH")


# --- Windows ---

def test_windows_dry_run_prints_schtasks(capsys):
    run = FakeRun()
    assert autostart.install(WIN_REPO, dry_run=True, target=win(), run=run) == 0
    out = capsys.readouterr().out
    name = windows.task_name(WIN_REPO)
    assert f'schtasks /Create /F /SC ONLOGON /RL LIMITED /TN "{name}" /TR ' in out
    assert str(WIN_CORE) in out and str(WIN_REPO) in out and run.calls == []
    assert autostart.uninstall(WIN_REPO, dry_run=True, target=win(), run=run) == 0
    assert f'schtasks /Delete /F /TN "{name}"' in capsys.readouterr().out and run.calls == []


def test_windows_tr_limit_refused(capsys):
    long_repo = Path("C:/Users/Jane Doe/" + "deep/" * 40 + "Tidepool")
    command = subprocess.list2cmdline(job_argv(win(), long_repo))
    assert len(command) > windows.TR_LIMIT
    for dry_run in (True, False):
        run = FakeRun()
        assert autostart.install(long_repo, dry_run=dry_run, target=win(), run=run) == 2
        err = capsys.readouterr().err
        assert str(len(command)) in err and str(windows.TR_LIMIT) in err and run.calls == []
        # The core of a plugin lives in Claude Code's own cache: the way out is the repo or a pip install.
        assert "move the repo to a shorter path, or install Nod with pip into a short path" in err
        assert "move Nod" not in err


def test_windows_tr_at_limit_is_accepted(capsys):
    base = subprocess.list2cmdline(job_argv(win(), Path("C:/r")))
    repo = Path("C:/r" + "x" * (windows.TR_LIMIT - len(base)))
    assert len(subprocess.list2cmdline(job_argv(win(), repo))) == windows.TR_LIMIT
    assert autostart.install(repo, dry_run=True, target=win(), run=FakeRun()) == 0


def test_windows_spaces_quoted(capsys):
    run = FakeRun(stdout="SUCCESS: created")
    assert autostart.install(WIN_REPO, dry_run=False, target=win(), run=run) == 0
    [(argv, kwargs)] = run.calls
    tr = subprocess.list2cmdline(job_argv(win(), WIN_REPO))
    assert argv == ["schtasks", "/Create", "/F", "/SC", "ONLOGON", "/RL", "LIMITED",
                    "/TN", windows.task_name(WIN_REPO), "/TR", tr]
    assert f'"{WIN_PYTHON}"' in tr and f'"{WIN_CORE}"' in tr and f'"{WIN_REPO}"' in tr and tr.endswith(" driver")
    assert kwargs["encoding"] == "oem" and kwargs["errors"] == "replace"
    assert "SUCCESS: created" in capsys.readouterr().out


def test_windows_returncode_and_missing_schtasks(capsys):
    assert autostart.install(WIN_REPO, dry_run=False, target=win(), run=FakeRun(code=3)) == 3
    assert autostart.uninstall(WIN_REPO, dry_run=False, target=win(), run=FakeRun(code=4)) == 4

    def missing(argv, **kwargs):
        raise FileNotFoundError(argv[0])
    with pytest.raises(CliError, match="could not run schtasks"):
        autostart.install(WIN_REPO, dry_run=False, target=win(), run=missing)
    status = autostart.status(WIN_REPO, target=win(), run=missing)
    assert status == JobStatus(False, False, windows.task_name(WIN_REPO))


# --- macOS ---

def test_macos_dry_run_prints_plist_and_launchctl(tmp_path, capsys):
    run = FakeRun()
    target = mac(tmp_path)
    assert autostart.install(MAC_REPO, dry_run=True, target=target, run=run) == 0
    out = capsys.readouterr().out
    data = plist_in(out)
    label = macos.label(MAC_REPO)
    log = str(MAC_REPO / ".nod" / "driver" / "autostart.log")
    assert data == {"Label": label, "ProgramArguments": job_argv(target, MAC_REPO), "RunAtLoad": True,
                    "WorkingDirectory": str(MAC_REPO), "StandardOutPath": log, "StandardErrorPath": log}
    path = macos.plist_path(target, MAC_REPO)
    assert str(path) in out and f"launchctl bootout gui/501/{label}" in out
    assert f"launchctl bootstrap gui/501 {shlex.quote(str(path))}" in out
    assert run.calls == [] and not path.exists() and not (tmp_path / "Library").exists()


def test_macos_spaces(tmp_path, capsys):
    home = tmp_path / "Jane Doe"
    target = mac(home)
    run = FakeRun()
    assert autostart.install(MAC_REPO, dry_run=True, target=target, run=run) == 0
    assert plist_in(capsys.readouterr().out)["ProgramArguments"][2] == str(SPACED)
    repo = tmp_path / "Tide pool"
    assert autostart.install(repo, dry_run=False, target=target, run=run) == 0
    path = macos.plist_path(target, repo)
    assert " " in str(path) and run.argvs[-1] == ["launchctl", "bootstrap", "gui/501", str(path)]
    assert plistlib.loads(path.read_bytes())["ProgramArguments"] == [POSIX_PYTHON, "-P", str(SPACED),
                                                                     "--root", str(repo), "driver"]


def test_macos_install_writes_plist_and_bootstraps(tmp_path, capsys):
    target = mac(tmp_path / "home")
    repo = tmp_path / "Tidepool"
    run = FakeRun()
    assert autostart.install(repo, dry_run=False, target=target, run=run) == 0
    path = macos.plist_path(target, repo)
    label = macos.label(repo)
    data = plistlib.loads(path.read_bytes())
    assert data["Label"] == label and data["RunAtLoad"] is True and data["WorkingDirectory"] == str(repo)
    assert data["StandardOutPath"] == str(repo / ".nod" / "driver" / "autostart.log")
    assert (repo / ".nod" / "driver").is_dir()
    assert run.argvs == [["launchctl", "bootout", f"gui/501/{label}"],
                         ["launchctl", "bootstrap", "gui/501", str(path)]]
    assert str(path) in capsys.readouterr().out
    failing = FakeRun(code=5)
    assert autostart.install(repo, dry_run=False, target=target, run=failing) == 5  # the bootstrap code


# --- Linux ---

def test_systemd_quote():
    assert linux.exec_quote('/home/Jane Doe/50%/a "b" $HOME \\x') == '"/home/Jane Doe/50%%/a \\"b\\" $$HOME \\\\x"'
    assert linux.exec_unquote(linux.exec_quote('/a b/50%/"c"/$d/\\e')) == '/a b/50%/"c"/$d/\\e'


def test_linux_systemd_unit_and_commands(tmp_path, capsys):
    xdg = tmp_path / "xdg"
    target = lin(tmp_path / "home", env={"XDG_CONFIG_HOME": str(xdg)})
    repo = tmp_path / "Tidepool"
    run = FakeRun(systemd=True)
    assert autostart.install(repo, dry_run=False, target=target, run=run) == 0
    unit = linux.unit_name(repo)
    path = xdg / "systemd" / "user" / unit
    text = path.read_text(encoding="utf-8")
    exec_line = next(line for line in text.splitlines() if line.startswith("ExecStart="))
    assert exec_line == "ExecStart=" + " ".join(linux.exec_quote(arg) for arg in job_argv(target, repo))
    assert "[Install]\nWantedBy=default.target" in text and "[Service]" in text
    assert run.argvs == [["systemctl", "--user", "show-environment"], ["systemctl", "--user", "daemon-reload"],
                         ["systemctl", "--user", "enable", "--now", unit]]
    assert run.crontab is None and not (tmp_path / "home" / ".config").exists()
    assert str(path) in capsys.readouterr().out


def test_linux_unit_counts_the_exit_after_a_stop_signal_as_success(tmp_path):
    """The driver exits with 128 + signal when systemd stops it; without the line `disable --now` leaves a `failed` unit."""
    text = linux.unit_text(lin(tmp_path / "home"), tmp_path / "Tidepool")
    assert "\nSuccessExitStatus=129 143\n" in text.split("[Install]")[0]
    assert signals.STOP_EXIT_CODES == (signals.EXIT_BASE + getattr(signal, "SIGHUP", 1), signals.EXIT_BASE + signal.SIGTERM)


def test_linux_systemd_spaces_and_percent(tmp_path):
    core = Path("/home/Jane Doe/50%/nod/the_nod/__main__.py")
    target = lin(tmp_path / "home", core=core)
    repo = tmp_path / "Tide pool"
    assert autostart.install(repo, dry_run=False, target=target, run=FakeRun()) == 0
    text = (linux.unit_dir(target) / linux.unit_name(repo)).read_text(encoding="utf-8")
    exec_line = next(line for line in text.splitlines() if line.startswith("ExecStart="))
    assert linux.exec_quote(str(core)) in exec_line and "50%%" in exec_line and "50%/" not in exec_line
    assert f'"{repo}"'.replace("\\", "\\\\") in exec_line
    status = autostart.status(repo, target=target, run=FakeRun())
    assert status == JobStatus(True, True, str(core))


def test_linux_falls_back_to_crontab(tmp_path, capsys):
    target = lin(tmp_path / "home")
    repo = tmp_path / "Tidepool"
    run = FakeRun(systemd=False, crontab=None)
    assert autostart.install(repo, dry_run=False, target=target, run=run) == 0
    line = f"@reboot {shlex.join(job_argv(target, repo))} # nod-driver-{job_suffix(repo)}"
    assert run.argvs == [["systemctl", "--user", "show-environment"], ["crontab", "-l"], ["crontab", "-"]]
    assert run.crontab == line + "\n" and not linux.unit_dir(target).exists()
    assert line in capsys.readouterr().out


def test_linux_crontab_escapes_percent(tmp_path):
    target = lin(tmp_path / "home", core=Path("/home/Jane Doe/50%/nod/the_nod/__main__.py"))
    repo = tmp_path / "Tidepool"
    run = FakeRun(systemd=False)
    assert autostart.install(repo, dry_run=False, target=target, run=run) == 0
    assert "50\\%" in run.crontab and "50%" not in run.crontab.replace("\\%", "")
    assert autostart.status(repo, target=target, run=run).detail == str(target.core)


def test_linux_systemctl_missing_falls_back_to_crontab(tmp_path):
    target = lin(tmp_path / "home")
    repo = tmp_path / "Tidepool"
    run = FakeRun()

    def no_systemctl(argv, **kwargs):
        if argv[0] == "systemctl":
            raise FileNotFoundError("systemctl")
        return run(argv, **kwargs)
    assert autostart.install(repo, dry_run=False, target=target, run=no_systemctl) == 0
    assert run.crontab.endswith(f"# nod-driver-{job_suffix(repo)}\n")


def test_crontab_keeps_foreign_lines_and_replaces_ours(tmp_path):
    target = lin(tmp_path / "home")
    repo = tmp_path / "Tidepool"
    tag = f"# nod-driver-{job_suffix(repo)}"
    foreign = ("SHELL=/bin/sh\n"
               "0 3 * * * /usr/local/bin/backup\n"
               f"@reboot /usr/bin/python3 -P /old/the_nod/__main__.py --root /srv/tidepool driver {tag}\n"
               "@reboot /usr/bin/python3 -P /x/the_nod/__main__.py --root /srv/other driver # nod-driver-00000000\n")
    run = FakeRun(systemd=False, crontab=foreign)
    assert autostart.install(repo, dry_run=False, target=target, run=run) == 0
    ours = f"@reboot {shlex.join(job_argv(target, repo))} {tag}"
    assert run.crontab == ("SHELL=/bin/sh\n0 3 * * * /usr/local/bin/backup\n"
                           "@reboot /usr/bin/python3 -P /x/the_nod/__main__.py --root /srv/other driver "
                           "# nod-driver-00000000\n" + ours + "\n")
    assert autostart.install(repo, dry_run=False, target=target, run=run) == 0
    assert run.crontab.count(tag) == 1


def test_linux_dry_run_prints_both_ways(tmp_path, capsys):
    target = lin(tmp_path / "home")
    repo = tmp_path / "Tidepool"
    run = FakeRun()
    assert autostart.install(repo, dry_run=True, target=target, run=run) == 0
    out = capsys.readouterr().out
    unit = linux.unit_name(repo)
    assert "ExecStart=" in out and "WantedBy=default.target" in out and str(linux.unit_dir(target) / unit) in out
    assert f"systemctl --user enable --now {unit}" in out and "systemctl --user daemon-reload" in out
    assert f"@reboot {shlex.join(job_argv(target, repo))} # nod-driver-{job_suffix(repo)}" in out
    assert run.calls == [] and not linux.unit_dir(target).exists()
    assert autostart.uninstall(repo, dry_run=True, target=target, run=run) == 0
    out = capsys.readouterr().out
    assert f"systemctl --user disable --now {unit}" in out and f"# nod-driver-{job_suffix(repo)}" in out
    assert run.calls == []


# --- uninstall and status ---

def test_uninstall_each_platform(tmp_path, capsys):
    run = FakeRun()
    assert autostart.uninstall(WIN_REPO, dry_run=False, target=win(), run=run) == 0
    assert run.argvs == [["schtasks", "/Delete", "/F", "/TN", windows.task_name(WIN_REPO)]]

    target = mac(tmp_path / "mac")
    repo = tmp_path / "Tidepool"
    autostart.install(repo, dry_run=False, target=target, run=FakeRun())
    path = macos.plist_path(target, repo)
    run = FakeRun(code=3)  # bootout of a job that is not loaded fails: it does not matter
    assert path.exists() and autostart.uninstall(repo, dry_run=False, target=target, run=run) == 0
    assert run.argvs == [["launchctl", "bootout", f"gui/501/{macos.label(repo)}"]] and not path.exists()
    assert autostart.uninstall(repo, dry_run=False, target=target, run=FakeRun()) == 0  # nothing left: still fine

    target = lin(tmp_path / "linux")
    unit = linux.unit_name(repo)
    autostart.install(repo, dry_run=False, target=target, run=FakeRun())
    line = f"@reboot {shlex.join(job_argv(target, repo))} # nod-driver-{job_suffix(repo)}\n"
    run = FakeRun(crontab="0 3 * * * /usr/local/bin/backup\n" + line)
    assert autostart.uninstall(repo, dry_run=False, target=target, run=run) == 0
    assert run.argvs == [["systemctl", "--user", "disable", "--now", unit], ["systemctl", "--user", "daemon-reload"],
                         ["crontab", "-l"], ["crontab", "-"]]
    assert run.crontab == "0 3 * * * /usr/local/bin/backup\n" and not (linux.unit_dir(target) / unit).exists()
    run = FakeRun(crontab="0 3 * * * /usr/local/bin/backup\n")
    assert autostart.uninstall(repo, dry_run=False, target=target, run=run) == 0
    assert run.argvs == [["crontab", "-l"]]  # neither a unit nor our line: nothing is written


def test_status_detects_stale_core(tmp_path):
    old, new = win(core=Path("C:/Users/Jane Doe/old/the_nod/__main__.py")), win()
    run = FakeRun(query=task_xml(old, WIN_REPO))
    assert autostart.status(WIN_REPO, target=new, run=run) == JobStatus(True, False, str(old.core))
    assert autostart.status(WIN_REPO, target=old, run=run) == JobStatus(True, True, str(old.core))
    assert run.argvs[0] == ["schtasks", "/Query", "/TN", windows.task_name(WIN_REPO), "/XML"]
    assert run.calls[0][1]["encoding"] == "oem"
    upper = win(core=Path(str(old.core).upper()))
    assert autostart.status(WIN_REPO, target=upper, run=run).current is True  # case does not matter on Windows
    assert autostart.status(WIN_REPO, target=new, run=FakeRun()) == JobStatus(False, False, windows.task_name(WIN_REPO))

    repo = tmp_path / "Tidepool"
    for make in (mac, lin):
        old, new = make(tmp_path / make.__name__, core=OLD_CORE), make(tmp_path / make.__name__)
        assert autostart.status(repo, target=new, run=FakeRun()).installed is False
        autostart.install(repo, dry_run=False, target=old, run=FakeRun())
        assert autostart.status(repo, target=new, run=FakeRun()) == JobStatus(True, False, str(OLD_CORE))
        assert autostart.status(repo, target=old, run=FakeRun()) == JobStatus(True, True, str(OLD_CORE))

    old, new = lin(tmp_path / "cron", core=OLD_CORE), lin(tmp_path / "cron")
    run = FakeRun(systemd=False)
    autostart.install(repo, dry_run=False, target=old, run=run)
    assert autostart.status(repo, target=new, run=run) == JobStatus(True, False, str(OLD_CORE))
    assert autostart.status(repo, target=old, run=run) == JobStatus(True, True, str(OLD_CORE))
    assert autostart.status(repo, target=new, run=FakeRun()) == JobStatus(False, False, linux.unit_name(repo))


def test_status_of_a_broken_job_is_installed_not_current(tmp_path):
    target = mac(tmp_path)
    repo = tmp_path / "Tidepool"
    path = macos.plist_path(target, repo)
    path.parent.mkdir(parents=True)
    for broken in (b"not a plist", b'<?xml version="1.0"?><plist><dict><key>a</key>', plistlib.dumps({"Label": 1})):
        path.write_bytes(broken)
        status = autostart.status(repo, target=target, run=FakeRun())
        assert status.installed is True and status.current is False and status.detail == str(path)
    run = FakeRun(query="<Task><broken")
    assert autostart.status(WIN_REPO, target=win(), run=run).current is False


# --- the CLI and doctor ---

def test_cli_dry_run_prints_the_job_of_this_machine(repo, capsys, monkeypatch):
    """The checkout's own path is not part of the check: a deep one would push the Windows /TR over its limit."""
    setup(repo, capsys)
    monkeypatch.setattr(autostart, "core_main", lambda: Path(repo.anchor, "deep" * 60, "the_nod", "__main__.py"))
    machine = autostart.current_target
    short = Path(repo.anchor, "nod", "the_nod", "__main__.py")
    monkeypatch.setattr(autostart, "current_target", lambda: dataclasses.replace(machine(), core=short))
    code, out, err = driver_run(repo, "install", "--dry-run", capsys=capsys)
    assert code == 0, err
    assert str(repo) in out or str(repo).replace("\\", "\\\\") in out
    expected = {"win32": "schtasks /Create", "darwin": "launchctl bootstrap"}.get(sys.platform, "systemctl --user")
    assert expected in out


def test_cli_passes_an_absolute_repo(repo, capsys, monkeypatch):
    setup(repo, capsys)
    seen = []
    monkeypatch.setattr(autostart, "install", lambda root, *, dry_run: seen.append(("install", root, dry_run)) or 0)
    monkeypatch.setattr(autostart, "uninstall", lambda root, *, dry_run: seen.append(("uninstall", root, dry_run)) or 0)
    monkeypatch.chdir(repo)
    assert main(["--root", ".", "driver", "install", "--dry-run"]) == 0
    assert main(["--root", ".", "driver", "uninstall"]) == 0
    here = Path(".").absolute()
    assert seen == [("install", here, True), ("uninstall", here, False)] and here.name == repo.name


def test_relative_root_doctor_asks_absolute_repo(repo, capsys, monkeypatch, tmp_path):
    setup(repo, capsys)
    asked = []
    m = Machine(home=tmp_path / "home", platform="linux", which=lambda n: "/usr/bin/" + n,
                has_module=lambda n: True, python_in_path=lambda: (3, 13),
                job_status=lambda root: asked.append(root) or JobStatus(False, False, "nod-driver-x.service"))
    monkeypatch.setattr(doctor, "machine", lambda: m)
    monkeypatch.chdir(repo)
    main(["--root", ".", "--json", "doctor"])
    capsys.readouterr()
    assert asked == [Path(".").absolute()] and asked[0].name == repo.name


def _job_pointing_at(platform: str, home: Path, repo: Path, core: Path):
    """A target of `platform` and a fake run whose machine holds our job, started with `core`."""
    if platform == "win32":
        return win(), FakeRun(query=task_xml(win(core=core), repo))
    make = mac if platform == "darwin" else lin
    autostart.install(repo, dry_run=False, target=make(home, core=core), run=FakeRun())
    return make(home), FakeRun()


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
def test_doctor_job_row_three_platforms(repo, capsys, tmp_path, monkeypatch, platform):
    main(["--root", str(repo), "init"])
    capsys.readouterr()

    def row(target, run):
        m = Machine(home=tmp_path / "home", platform=platform, which=lambda n: "/usr/bin/" + n,
                    has_module=lambda n: True, python_in_path=lambda: (3, 13),
                    job_status=lambda root: autostart.status(root, target=target, run=run))
        monkeypatch.setattr(doctor, "machine", lambda: m)
        capsys.readouterr()  # what setting the job up printed
        main(["--root", str(repo), "--json", "doctor"])
        out = json.loads(capsys.readouterr().out)
        return next(c for c in out["checks"] if c["name"] == "driver job")

    empty = {"win32": win(), "darwin": mac(tmp_path / "empty"), "linux": lin(tmp_path / "empty")}[platform]
    missing = row(empty, FakeRun())
    assert missing["ok"] is False and missing["detail"].startswith("job ") and missing["fix"] == "nod driver install"

    target, run = _job_pointing_at(platform, tmp_path / "stale", repo, OLD_CORE)
    stale = row(target, run)
    assert stale == {"name": "driver job", "ok": False, "detail": f"points to {OLD_CORE}",
                     "fix": "nod driver install", "auto": "job"}
    main(["--root", str(repo), "doctor"])
    assert re.search(r"driver job\s+no \(points to .*\)\s+nod driver install", capsys.readouterr().out)

    target, run = _job_pointing_at(platform, tmp_path / "current", repo, target.core)
    assert row(target, run) == {"name": "driver job", "ok": True, "detail": "exists", "fix": "—", "auto": None}
    main(["--root", str(repo), "doctor"])
    assert re.search(r"driver job\s+yes\s", capsys.readouterr().out + " ")


# --- the language ---

def test_texts_in_russian(tmp_path, capsys):
    i18n.use("ru")
    target = mac(tmp_path)
    assert autostart.install(MAC_REPO, dry_run=True, target=target, run=FakeRun()) == 0
    out = capsys.readouterr().out
    assert "записал бы" in out and "запустил бы" in out
    long_repo = Path("C:/" + "deep/" * 60)
    assert autostart.install(long_repo, dry_run=True, target=win(), run=FakeRun()) == 2
    err = capsys.readouterr().err
    assert err.startswith("ошибка: ") and str(windows.TR_LIMIT) in err
    assert "перенеси репу на путь короче или поставь Nod через pip в короткий путь" in err


def test_texts_in_english_have_no_cyrillic(capsys):
    homes = Path("/Users/Jane Doe"), Path("/home/Jane Doe")
    for target, repo in ((win(), WIN_REPO), (mac(homes[0]), MAC_REPO), (lin(homes[1]), LINUX_REPO)):
        autostart.install(repo, dry_run=True, target=target, run=FakeRun())
        autostart.uninstall(repo, dry_run=True, target=target, run=FakeRun())
    out = capsys.readouterr()
    assert not CYRILLIC.search(out.out + out.err)


# --- the PATH of the installing shell goes into the job ---

SPACED_PATH = "/opt/home brew/bin:/home/Jane Doe/.local/bin:/x/50%/$y:/usr/bin:/bin"


def test_job_path_is_the_installing_shell_path():
    assert autostart.job_path(lin(Path("/h"), env={"PATH": SPACED_PATH})) == SPACED_PATH
    assert autostart.job_path(lin(Path("/h"), env={"PATH": "  "})) is None
    assert autostart.job_path(lin(Path("/h"))) is None


def test_macos_plist_carries_path(tmp_path, capsys):
    target = mac(tmp_path / "home", env={"PATH": SPACED_PATH})
    repo = tmp_path / "Tidepool"
    assert autostart.install(repo, dry_run=True, target=target, run=FakeRun()) == 0
    assert plist_in(capsys.readouterr().out)["EnvironmentVariables"] == {"PATH": SPACED_PATH}
    assert autostart.install(repo, dry_run=False, target=target, run=FakeRun()) == 0
    data = plistlib.loads(macos.plist_path(target, repo).read_bytes())
    assert data["EnvironmentVariables"] == {"PATH": SPACED_PATH} and data["ProgramArguments"] == job_argv(target, repo)
    assert "EnvironmentVariables" not in plistlib.loads(macos.plist_bytes(mac(tmp_path), repo))


def test_systemd_unit_carries_path(tmp_path):
    target = lin(tmp_path / "home", env={"PATH": SPACED_PATH})
    repo = tmp_path / "Tidepool"
    text = linux.unit_text(target, repo)
    [line] = [line for line in text.splitlines() if line.startswith("Environment=")]
    assert line == 'Environment="PATH=/opt/home brew/bin:/home/Jane Doe/.local/bin:/x/50%%/$y:/usr/bin:/bin"'
    assert linux.exec_unquote(line.removeprefix("Environment="), expand=False) == f"PATH={SPACED_PATH}"
    assert text.index("Environment=") < text.index("ExecStart=") and "[Service]\nEnvironment=" in text
    assert "Environment=" not in linux.unit_text(lin(tmp_path / "home"), repo)


def test_crontab_line_carries_path_for_our_command_only(tmp_path):
    target = lin(tmp_path / "home", env={"PATH": SPACED_PATH})
    repo = tmp_path / "Tidepool"
    run = FakeRun(systemd=False, crontab="0 3 * * * /usr/local/bin/backup\n")
    assert autostart.install(repo, dry_run=False, target=target, run=run) == 0
    first, ours = run.crontab.splitlines()
    assert first == "0 3 * * * /usr/local/bin/backup" and not any(l.startswith("PATH=") for l in run.crontab.split("\n"))
    command = ours.removeprefix("@reboot ").removesuffix(f" # nod-driver-{job_suffix(repo)}")
    assert shlex.split(command.replace(r"\%", "%")) == ["/usr/bin/env", f"PATH={SPACED_PATH}", *job_argv(target, repo)]
    assert r"50\%" in command
    assert autostart.status(repo, target=target, run=run) == JobStatus(True, True, str(target.core))


def _cron_path_of(line: str) -> list[str]:
    """The PATH entries a crontab line sets for our command."""
    command = line.removeprefix("@reboot ").split(" # nod-driver-")[0]
    return shlex.split(command)[1].removeprefix("PATH=").split(":")


def _cron_bytes(line: str) -> int:
    """What cron counts: the bytes of the command after `@reboot`."""
    return len(line.removeprefix("@reboot ").rstrip("\n").encode("utf-8"))


@pytest.fixture(autouse=True)
def no_claude_on_the_made_up_path(monkeypatch):
    """The cron tests use made-up PATHs; a real `claude` of the machine must decide nothing (only in `linux`)."""
    monkeypatch.setattr(linux, "shutil", SimpleNamespace(which=lambda name, path=None: None))


def claude_in(monkeypatch, found: str | None) -> list[tuple]:
    """`shutil.which` of `linux` answers `found`; the returned list collects the calls."""
    calls: list[tuple] = []

    def which(name, path=None):
        calls.append((name, path))
        return found

    monkeypatch.setattr(linux, "shutil", SimpleNamespace(which=which))
    return calls


WSL_PATH = ":".join(["/home/jane/.local/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/bin",
                     *(f"/mnt/c/Program Files/Tool {n}/bin" for n in range(40))])


def test_crontab_line_drops_the_windows_path_that_cron_would_refuse(tmp_path, capsys):
    """WSL appends the Windows PATH; cron answers a command over 998 bytes with "command too long"."""
    target = lin(tmp_path / "home", env={"PATH": WSL_PATH})
    repo = tmp_path / "Tidepool"
    run = FakeRun(systemd=False)
    assert len(WSL_PATH) > linux.CRON_COMMAND_LIMIT
    assert autostart.install(repo, dry_run=False, target=target, run=run) == 0
    line = run.crontab.rstrip("\n")
    assert _cron_bytes(line) <= linux.CRON_COMMAND_LIMIT
    assert _cron_path_of(line) == ["/home/jane/.local/bin", "/usr/local/bin", "/usr/bin", "/bin"]
    assert "PATH is cut from 45 to 4 directories" in capsys.readouterr().out
    assert autostart.status(repo, target=target, run=run) == JobStatus(True, True, str(target.core))


def test_crontab_line_drops_duplicates_before_anything_else(tmp_path):
    path = ":".join(["/usr/local/bin", "/usr/bin", "/bin"] * 120)
    target = lin(tmp_path / "home", env={"PATH": path})
    assert _cron_path_of(linux.cron_line(target, tmp_path / "Tidepool")) == ["/usr/local/bin", "/usr/bin", "/bin"]


def test_crontab_line_cuts_the_tail_of_a_path_that_is_long_by_itself(tmp_path):
    entries = [f"/opt/tools/{n:03d}/{'x' * 20}" for n in range(80)]
    target = lin(tmp_path / "home", env={"PATH": ":".join(entries)})
    kept = _cron_path_of(linux.cron_line(target, tmp_path / "Tidepool"))
    assert 0 < len(kept) < len(entries) and kept == entries[:len(kept)]
    assert _cron_bytes(linux.cron_line(target, tmp_path / "Tidepool")) <= linux.CRON_COMMAND_LIMIT


def test_crontab_line_keeps_a_short_path_as_it_is(tmp_path, capsys, monkeypatch):
    path = "/usr/bin:/bin:/usr/bin"  # a duplicate stays: nothing is too long
    target = lin(tmp_path / "home", env={"PATH": path})
    asked = claude_in(monkeypatch, None)
    assert _cron_path_of(linux.cron_line(target, tmp_path / "Tidepool")) == path.split(":")
    assert autostart.install(tmp_path / "Tidepool", dry_run=True, target=target, run=FakeRun(systemd=False)) == 0
    assert "cut from" not in capsys.readouterr().out and asked == []  # claude is not looked for when nothing is cut


# cron counts bytes of the command, a Cyrillic letter is two of them
CYRILLIC_ENTRIES = ["/usr/local/bin", "/usr/bin", "/bin", *(f"/home/Иван/инструменты/{n:02d}" for n in range(24))]


def test_crontab_limit_counts_bytes_not_characters(tmp_path, capsys):
    """A line of 962 characters and 1183 bytes made `crontab -` fail with "command too long" on a live WSL."""
    repo = Path("/home/jane/Проект")
    target = lin(tmp_path / "home", env={"PATH": ":".join(CYRILLIC_ENTRIES)})
    whole = linux._cron_command(target, repo, ":".join(CYRILLIC_ENTRIES))
    assert len(whole) <= linux.CRON_COMMAND_LIMIT < len(whole.encode("utf-8"))  # fits by characters, not by bytes
    run = FakeRun(systemd=False)
    assert autostart.install(repo, dry_run=False, target=target, run=run) == 0
    line = run.raw.decode("utf-8").rstrip("\n")
    assert _cron_bytes(line) <= linux.CRON_COMMAND_LIMIT
    kept = _cron_path_of(line)
    assert CYRILLIC_ENTRIES[:3] == kept[:3] and 3 < len(kept) < len(CYRILLIC_ENTRIES) and kept == CYRILLIC_ENTRIES[:len(kept)]
    assert f"PATH is cut from {len(CYRILLIC_ENTRIES)} to {len(kept)} directories" in capsys.readouterr().out
    assert "Проект" in line  # the non-ASCII repo path reaches cron as it is


NPM = "/mnt/c/Users/Jane/AppData/Roaming/npm"
WINDOWS_WITH_NPM = ["/home/jane/.local/bin", "/usr/local/bin", "/usr/bin", "/bin",
                    *(f"/mnt/c/Program Files/Tool {n}/bin" for n in range(20)), NPM,
                    *(f"/mnt/c/Program Files/More {n}/bin" for n in range(20))]


def test_crontab_line_keeps_the_folder_of_claude_on_the_windows_drive(tmp_path, capsys, monkeypatch):
    path = ":".join(WINDOWS_WITH_NPM)
    asked = claude_in(monkeypatch, NPM + "/claude")
    target = lin(tmp_path / "home", env={"PATH": path})
    line = linux.cron_line(target, tmp_path / "Tidepool")
    assert _cron_path_of(line) == [*WINDOWS_WITH_NPM[:4], NPM]  # in the order of the shell
    assert _cron_bytes(line) <= linux.CRON_COMMAND_LIMIT
    assert set(asked) == {("claude", path)}  # looked up the way the shell does, on the whole PATH
    assert autostart.install(tmp_path / "Tidepool", dry_run=True, target=target, run=FakeRun(systemd=False)) == 0
    out = capsys.readouterr().out
    assert "PATH is cut from 45 to 5 directories" in out and "will not find claude" not in out


def test_crontab_line_keeps_the_folder_of_claude_at_the_tail(tmp_path, monkeypatch):
    nvm = "/home/jane/.nvm/versions/node/v22.1.0/bin"
    entries = [f"/opt/tools/{n:03d}/{'x' * 20}" for n in range(80)] + [nvm]
    claude_in(monkeypatch, nvm + "/claude")
    target = lin(tmp_path / "home", env={"PATH": ":".join(entries)})
    line = linux.cron_line(target, tmp_path / "Tidepool")
    kept = _cron_path_of(line)
    assert kept[-1] == nvm and kept[:-1] == entries[:len(kept) - 1] and 1 < len(kept) < len(entries)
    assert _cron_bytes(line) <= linux.CRON_COMMAND_LIMIT


def test_crontab_line_warns_when_the_folder_of_claude_does_not_fit(tmp_path, capsys, monkeypatch):
    far = "/srv/" + "very-long-folder/" * 70 + "bin"  # alone over the limit
    entries = ["/usr/bin", "/bin", far]
    claude_in(monkeypatch, far + "/claude")
    target = lin(tmp_path / "home", env={"PATH": ":".join(entries)})
    assert autostart.install(tmp_path / "Tidepool", dry_run=False, target=target, run=FakeRun(systemd=False)) == 0
    out = capsys.readouterr().out
    assert f"{far} holds claude and had to be cut from PATH" in out and "will not find claude" in out
    assert "PATH is cut from 3 to 2 directories" in out  # the others stay: nothing is cut for a folder that cannot stay
    assert _cron_path_of(linux.cron_line(target, tmp_path / "Tidepool")) == ["/usr/bin", "/bin"]


def test_crontab_line_says_the_default_path_of_cron_is_used_when_nothing_fits(tmp_path, capsys, monkeypatch):
    entries = [f"/srv/{n}/" + "very-long-folder/" * 70 + "bin" for n in range(3)]
    claude_in(monkeypatch, entries[1] + "/claude")
    target = lin(tmp_path / "home", env={"PATH": ":".join(entries)})
    run = FakeRun(systemd=False)
    assert autostart.install(tmp_path / "Tidepool", dry_run=False, target=target, run=run) == 0
    line = run.crontab.rstrip("\n")
    assert "PATH=" not in line and _cron_bytes(line) <= linux.CRON_COMMAND_LIMIT
    out = capsys.readouterr().out
    assert "none of the 3 PATH directories fits: the job gets the default PATH of cron" in out
    assert "will not find claude" in out
    claude_in(monkeypatch, None)  # no claude on the PATH: no second warning
    assert autostart.install(tmp_path / "Tidepool", dry_run=True, target=target, run=FakeRun(systemd=False)) == 0
    out = capsys.readouterr().out
    assert "default PATH of cron" in out and "will not find claude" not in out


def test_crontab_path_notes_follow_the_language(tmp_path, capsys):
    i18n.use("ru")
    target = lin(tmp_path / "home", env={"PATH": WSL_PATH})
    assert autostart.install(tmp_path / "Tidepool", dry_run=True, target=target, run=FakeRun(systemd=False)) == 0
    assert "PATH сокращён с 45 до 4 каталогов" in capsys.readouterr().out


def test_windows_task_ignores_path():
    target = Target(platform="win32", home=Path("C:/Users/Jane Doe"), python=WIN_PYTHON, core=WIN_CORE, uid=None,
                    env={"PATH": "C:/Program Files/Git/cmd;C:/Users/Jane Doe/.local/bin"})
    assert windows.install_argv(target, WIN_REPO) == windows.install_argv(win(), WIN_REPO)


# --- foreign crontab lines go back byte for byte ---

def test_crontab_round_trips_foreign_bytes(tmp_path):
    target = lin(tmp_path / "home")
    repo = tmp_path / "Tidepool"
    tag = f"# nod-driver-{job_suffix(repo)}".encode()
    foreign = (b"SHELL=/bin/sh\n"
               b"0 3 * * * /usr/local/bin/backup --note \x0cpage\r\n"
               b"@weekly echo caf\xe9 \xff\xfe\n")
    run = FakeRun(systemd=False, crontab=foreign + b"@reboot /old/python -P /old/core driver " + tag + b"\n")
    assert autostart.install(repo, dry_run=False, target=target, run=run) == 0
    ours = linux.cron_line(target, repo).encode()
    assert run.raw == foreign + ours + b"\n"
    assert autostart.status(repo, target=target, run=run).installed is True
    assert autostart.uninstall(repo, dry_run=False, target=target, run=run) == 0
    assert run.raw == foreign


# --- systemd quoting of the program path ---

def test_systemd_program_path_keeps_its_dollar(tmp_path):
    target = Target(platform="linux", home=tmp_path / "home", python="/opt/py$3 dir/python3",
                    core=Path("/home/Jane Doe/$nod/the_nod/__main__.py"), uid=1000, env={})
    repo = tmp_path / "Tidepool"
    exec_line = next(l for l in linux.unit_text(target, repo).splitlines() if l.startswith("ExecStart="))
    assert exec_line.startswith('ExecStart="/opt/py$3 dir/python3" "-P" ')
    assert linux.exec_quote(str(target.core)) in exec_line and "$$nod" in exec_line
    assert autostart.install(repo, dry_run=False, target=target, run=FakeRun()) == 0
    assert autostart.status(repo, target=target, run=FakeRun()) == JobStatus(True, True, str(target.core))
    assert linux._unit_args(linux.unit_dir(target) / linux.unit_name(repo))[0] == "/opt/py$3 dir/python3"


# --- a failed systemctl step ---

@pytest.mark.parametrize("failing", ["systemctl --user daemon-reload", "systemctl --user enable"])
def test_linux_failed_systemctl_removes_the_unit(tmp_path, capsys, failing):
    target = lin(tmp_path / "home")
    repo = tmp_path / "Tidepool"
    unit = linux.unit_name(repo)
    run = FakeRun(fails={failing: (1, "Failed to connect to bus")})
    assert autostart.install(repo, dry_run=False, target=target, run=run) == 1
    assert not (linux.unit_dir(target) / unit).exists()
    tried = [["systemctl", "--user", "daemon-reload"]]
    if failing.endswith("enable"):
        tried.append(["systemctl", "--user", "enable", "--now", unit])
    assert run.argvs == [["systemctl", "--user", "show-environment"], *tried,
                         ["systemctl", "--user", "disable", "--now", unit], ["systemctl", "--user", "daemon-reload"]]
    err = capsys.readouterr().err
    assert "Failed to connect to bus" in err and f"{failing}" in err and "returned code 1" in err
    assert autostart.status(repo, target=target, run=FakeRun()).installed is False


def test_linux_failed_disable_keeps_the_unit_and_fails(tmp_path, capsys):
    target = lin(tmp_path / "home")
    repo = tmp_path / "Tidepool"
    autostart.install(repo, dry_run=False, target=target, run=FakeRun())
    path = linux.unit_dir(target) / linux.unit_name(repo)
    capsys.readouterr()
    line = linux.cron_line(target, repo)
    run = FakeRun(fails={"systemctl --user disable": (1, "Failed to disable unit: Access denied")},
                  crontab=f"0 3 * * * /usr/local/bin/backup\n{line}\n")
    assert autostart.uninstall(repo, dry_run=False, target=target, run=run) == 1
    err = capsys.readouterr().err
    assert "Failed to disable unit: Access denied" in err and f"{path}" in err
    assert path.exists() and run.crontab == "0 3 * * * /usr/local/bin/backup\n"  # the crontab is still cleaned
    assert ["systemctl", "--user", "daemon-reload"] not in run.argvs
    assert autostart.status(repo, target=target, run=run).installed is True
