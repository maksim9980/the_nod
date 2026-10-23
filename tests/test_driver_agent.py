"""Running the agent command: the prompt on stdin, the hang check, the heartbeat, the git hooks."""
import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
import pytest
from the_nod.cli import main
from the_nod.commands import driver as driver_command
from the_nod.driver import agent, signals
from tests.driver_helpers import REPO_ROOT, add_card, fake, setup

def go(mode, tmp_path, **kw):
    env = {"NOD_RESULT": str(tmp_path / "r.toml"), "NOD_ROOT": str(tmp_path)}
    args = dict(cwd=tmp_path, stdin="привет", env=env, activity=lambda: 0.0, stuck_after=30.0)
    return agent.run_command(fake(mode), **{**args, **kw})

def test_exit_with_stdout(tmp_path):
    out = go("echo", tmp_path)
    assert out.status == "exit" and out.code == 0 and "привет" in out.stdout

def test_nonzero_exit(tmp_path):
    assert go("fail", tmp_path).code == 1

def test_stuck_kills_after_limit(tmp_path):
    t = time.monotonic(); out = go("hang", tmp_path, stuck_after=1.0)
    assert out.status == "stuck" and time.monotonic() - t < 10

def test_activity_file_prevents_kill(tmp_path):
    f = tmp_path / "r.toml.activity"
    out = go("touch", tmp_path, stuck_after=1.0, activity=lambda: f.stat().st_mtime if f.exists() else 0.0)
    assert out.status == "exit" and out.code == 0

def test_tick_called_and_errors_swallowed(tmp_path):
    calls = []
    def tick(): calls.append(1); raise RuntimeError("heartbeat failed")
    out = go("hang", tmp_path, stuck_after=1.5, tick=tick, tick_every=0.4)
    assert len(calls) >= 2 and "heartbeat failed" in out.stderr

def test_spawn_error_on_missing_cwd(tmp_path):
    out = agent.run_command("x", cwd=tmp_path / "missing", stdin="", env={}, activity=lambda: 0.0, stuck_after=1.0)
    assert out.status == "spawn-error" and out.stderr

def test_git_hooks_disabled_for_command(repo, tmp_path):
    hooks = tmp_path / "no-hooks"
    out = agent.run_command("git config core.hooksPath", cwd=repo, stdin="", env={}, activity=lambda: 0.0, stuck_after=10.0, hooks_dir=hooks)
    assert out.code == 0 and out.stdout.strip() == hooks.as_posix() and hooks.is_dir()

def test_hooks_snapshot_ignores_samples(repo):
    folder = agent.hooks_folder(repo)
    folder.mkdir(exist_ok=True)
    (folder / "pre-commit.sample").write_text("x", encoding="utf-8")
    assert agent.hooks_snapshot(folder) == {}
    (folder / "pre-commit").write_text("x", encoding="utf-8")
    before = agent.hooks_snapshot(folder)
    assert list(before) == ["pre-commit"] and len(before["pre-commit"]) == 64
    (folder / "pre-commit").write_text("y", encoding="utf-8")
    assert agent.hooks_snapshot(folder) != before
    assert agent.hooks_snapshot(repo / "missing") == {}

def test_hooks_folder_ignores_hooks_path_config(repo):
    subprocess.run(["git", "config", "core.hooksPath", "other"], cwd=repo, check=True)
    assert agent.hooks_folder(repo).resolve() == (repo / ".git" / "hooks").resolve()

def test_config_snapshot_changes_with_config(repo):
    before = agent.config_snapshot(repo)
    assert before and len(before) == 64
    subprocess.run(["git", "config", "x.y", "z"], cwd=repo, check=True)
    assert agent.config_snapshot(repo) != before

def script(tmp_path, body):
    path = tmp_path / "inline.py"
    path.write_text(body, encoding="utf-8")
    return f'"{sys.executable}" "{path}"'

def test_slow_output_is_activity(tmp_path):
    cmd = script(tmp_path, "import time, sys\n"
                 "for i in range(4):\n"
                 "    print(i); sys.stdout.flush(); time.sleep(0.5)\n")
    out = agent.run_command(cmd, cwd=tmp_path, stdin="", env={}, activity=lambda: 0.0, stuck_after=1.2)
    assert out.status == "exit" and "3" in out.stdout

def test_grandchild_holding_pipe_does_not_block(tmp_path):
    cmd = script(tmp_path, "import subprocess, sys\n"
                 "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])\n"
                 "print(p.pid, flush=True)\n")
    t = time.monotonic()
    out = agent.run_command(cmd, cwd=tmp_path, stdin="", env={}, activity=lambda: 0.0, stuck_after=30.0)
    spent = time.monotonic() - t
    pid = out.stdout.strip().split()[0]
    try:
        assert out.status == "exit" and spent < 10
    finally:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        else:
            try:
                os.kill(int(pid), signal.SIGKILL)
            except OSError:
                pass

def test_activity_error_counts_as_no_activity(tmp_path):
    def broken():
        raise OSError("busy")
    out = go("echo", tmp_path, activity=broken)
    assert out.status == "exit" and out.code == 0

def test_git_env_escapes_quote_and_keeps_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "'user.name=x'")
    value = agent.git_env(tmp_path / "it's")["GIT_CONFIG_PARAMETERS"]
    assert value.startswith("'user.name=x' 'core.hooksPath=") and value.endswith(r"it'\''s'")
    monkeypatch.delenv("GIT_CONFIG_PARAMETERS")
    assert agent.git_env(tmp_path / "h")["GIT_CONFIG_PARAMETERS"].startswith("'core.hooksPath=")

def test_run_command_starts_a_new_session_on_posix(tmp_path, monkeypatch):
    seen = {}
    def fake_popen(command, **kwargs):
        seen.update(kwargs)
        raise OSError("no shell")
    monkeypatch.setattr(agent.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(agent.sys, "platform", "linux")
    out = agent.run_command("x", cwd=tmp_path, stdin="", env={}, activity=lambda: 0.0, stuck_after=1.0)
    assert out.status == "spawn-error" and seen["start_new_session"] is True and seen["creationflags"] == 0

def test_kill_tree_kills_the_group_on_posix(monkeypatch):
    killed, waited = [], []
    proc = SimpleNamespace(pid=4242, kill=lambda: killed.append("kill"), wait=lambda timeout: waited.append(timeout))
    monkeypatch.setattr(agent.sys, "platform", "linux")
    monkeypatch.setattr(agent.signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(agent.os, "killpg", lambda pid, sig: killed.append((pid, sig)), raising=False)
    agent.kill_tree(proc)
    assert killed == [(4242, 9)] and waited == [agent.KILL_WAIT]
    def gone(pid, sig):
        raise ProcessLookupError(pid)
    monkeypatch.setattr(agent.os, "killpg", gone, raising=False)
    killed.clear()
    agent.kill_tree(proc)
    assert killed == ["kill"]  # no group left: the process itself is killed

def _gone(pid: int, wait: float = 5.0) -> bool:
    """The process is gone, or a zombie nobody reaped yet (a container without init)."""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        stat = Path(f"/proc/{pid}/stat")
        try:
            if stat.read_text().rsplit(")", 1)[1].split()[0] == "Z":
                return True
        except (OSError, IndexError):
            pass
        time.sleep(0.1)
    return False

@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
def test_kill_tree_kills_grandchild_posix(tmp_path):
    pid_file = tmp_path / "grandchild.pid"
    cmd = script(tmp_path, "import subprocess, sys, time\n"
                 "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                 f"open({str(pid_file)!r}, 'w').write(str(p.pid))\n"
                 "time.sleep(60)\n")
    out = agent.run_command(cmd, cwd=tmp_path, stdin="", env={}, activity=lambda: 0.0, stuck_after=1.5)
    pid = int(pid_file.read_text())
    try:
        assert out.status == "stuck" and _gone(pid)
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


# --- a signal to the driver stops the agent too ---

def test_driver_once_and_loop_run_inside_exit_on_signals(repo, capsys, monkeypatch):
    setup(repo, capsys)
    inside, seen = [], []

    @contextlib.contextmanager
    def recording():
        inside.append(True)
        yield
        inside.pop()
    monkeypatch.setattr(signals, "exit_on_signals", recording)
    monkeypatch.setattr(driver_command, "_once", lambda args: seen.append(("once", list(inside))) or 0)
    monkeypatch.setattr(driver_command.loop, "run_loop", lambda args, **kw: seen.append(("loop", list(inside))) or 0)
    assert main(["--root", str(repo), "driver", "once"]) == 0
    assert main(["--root", str(repo), "driver", "--passes", "1"]) == 0
    assert seen == [("once", [True]), ("loop", [True])] and inside == []


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows branch")
def test_exit_on_signals_changes_nothing_on_windows():
    before = signal.getsignal(signal.SIGTERM)
    with signals.exit_on_signals():
        assert signal.getsignal(signal.SIGTERM) is before


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_exit_on_signals_raises_system_exit_and_restores():
    before = {name: signal.getsignal(getattr(signal, name)) for name in signals.STOP_SIGNALS}
    for name in signals.STOP_SIGNALS:
        number = getattr(signal, name)
        with pytest.raises(SystemExit) as stopped:
            with signals.exit_on_signals():
                os.kill(os.getpid(), number)
                time.sleep(5)  # the handler interrupts the sleep
        assert stopped.value.code == signals.EXIT_BASE + number
    assert {name: signal.getsignal(getattr(signal, name)) for name in signals.STOP_SIGNALS} == before


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_exit_on_signals_keeps_an_ignored_sighup():
    """`nohup nod driver &` ignores SIGHUP on purpose: closing that terminal must not stop the driver."""
    previous = signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        with signals.exit_on_signals():
            assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
            assert signal.getsignal(signal.SIGTERM) is signals._exit
            os.kill(os.getpid(), signal.SIGHUP)
            time.sleep(0.2)  # ignored: no SystemExit
        assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
    finally:
        signal.signal(signal.SIGHUP, previous)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals and process groups")
def test_sigterm_to_the_driver_kills_the_agent_group(repo, capsys, tmp_path):
    setup(repo, capsys, brief="spawn-hang")
    add_card(repo, capsys)
    pid_file = tmp_path / "grandchild.pid"
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "FAKE_GRANDCHILD_PID": str(pid_file),
           "HOME": str(tmp_path / "home")}
    for name in ("NOD_AGENT", "NOD_LANG"):
        env.pop(name, None)
    driver = subprocess.Popen([sys.executable, "-m", "the_nod", "--root", str(repo), "driver", "once"], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pid = None
    try:
        deadline = time.monotonic() + 60
        while pid is None and time.monotonic() < deadline and driver.poll() is None:
            text = pid_file.read_text(encoding="utf-8").strip() if pid_file.exists() else ""
            pid = int(text) if text else None
            time.sleep(0.1)
        assert pid is not None, driver.communicate(timeout=10)
        driver.send_signal(signal.SIGTERM)
        assert driver.wait(timeout=30) == signals.EXIT_BASE + signal.SIGTERM
        assert _gone(pid)
    finally:
        if driver.poll() is None:
            driver.kill()
        if pid is not None:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
