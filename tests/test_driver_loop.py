"""The driver loop: a pass at once, then on a state change, after work and by the timer."""
import time
from the_nod.cli import main
from the_nod.driver import loop
from the_nod.store import Store
from tests.driver_helpers import driver_run, env_for_tests, setup

def test_loop_passes_limit_and_mtime_trigger(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); setup(repo, capsys)
    monkeypatch.setattr(loop, "PULL_EVERY_SECONDS", 3600.0)
    code, out, _ = driver_run(repo, "--interval", "0.1", "--passes", "2", capsys=capsys)
    assert code == 0 and out.count("pain:") == 1 and out.count("idle:") == 1

def test_loop_runs_pass_only_on_change(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); setup(repo, capsys)
    monkeypatch.setattr(loop, "PULL_EVERY_SECONDS", 3600.0)
    calls = []
    monkeypatch.setattr(loop.once, "run_pass", lambda args, log: calls.append(1) or loop.once.PassResult("idle", ""))
    import threading
    t = threading.Thread(target=lambda: driver_run(repo, "--interval", "0.1", "--passes", "2", capsys=capsys), daemon=True); t.start()
    time.sleep(0.5); assert calls == [1]
    main(["--root", str(repo), "card", "add", "Weekly email digest"]); t.join(5)
    assert not t.is_alive() and calls == [1, 1]

def test_loop_stops_on_keyboard_interrupt(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    def boom(args, log): raise KeyboardInterrupt
    monkeypatch.setattr(loop.once, "run_pass", boom)
    code, _, _ = driver_run(repo, "--interval", "0.1", capsys=capsys)
    assert code == 0 and "stopped by the owner" in (s.root / "driver.log").read_text(encoding="utf-8")
    assert not (s.root / "driver" / "pid").exists()

def test_loop_error_pass_is_quiet_until_state_changes(repo, capsys, monkeypatch, tmp_path):
    import argparse, threading
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    monkeypatch.setattr(loop, "PULL_EVERY_SECONDS", 3600.0)
    calls = []
    def broken(args, log):
        calls.append(1)
        if len(calls) > 3: raise KeyboardInterrupt
        raise RuntimeError("broken file")
    monkeypatch.setattr(loop.once, "run_pass", broken)
    t = threading.Thread(target=lambda: loop.run_loop(argparse.Namespace(root=str(repo)), interval=0.05, passes=0), daemon=True)
    t.start()
    time.sleep(0.5); assert len(calls) == 1
    for n in (2, 3):
        (s.root / "cards" / f"touch-{n}.md").write_text("x", encoding="utf-8")
        deadline = time.monotonic() + 3
        while len(calls) < n and time.monotonic() < deadline: time.sleep(0.05)
        assert len(calls) == n
        time.sleep(0.3); assert len(calls) == n
    (s.root / "cards" / "touch-4.md").write_text("x", encoding="utf-8")
    t.join(5)
    assert not t.is_alive() and len(calls) == 4


def foreign_host(s, host="desktop"):
    path = s.root / "harness.toml"
    path.write_text(path.read_text(encoding="utf-8").replace('driver_host = ""', f'driver_host = "{host}"'), encoding="utf-8")

def test_loop_exits_2_on_the_first_pass_when_driver_host_is_another_machine(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys); foreign_host(s)
    monkeypatch.setattr(loop, "PULL_EVERY_SECONDS", 0.2)  # without the stop the loop ends its passes and exits 0, not hangs
    started = time.monotonic()
    code, out, err = driver_run(repo, "--interval", "0.1", "--passes", "3", capsys=capsys)
    assert code == 2 and err.strip() == "error: the driver of this project runs on desktop"
    log = (s.root / "driver.log").read_text(encoding="utf-8")
    assert log.count("the driver of this project runs on desktop") == 1 and "ERROR" in log
    assert "pass" not in log and not (s.root / "driver" / "pid").exists()
    assert time.monotonic() - started < 5  # no waiting for the next passes

def test_loop_exits_2_when_driver_host_changes_to_another_machine(repo, capsys, monkeypatch, tmp_path):
    import argparse, threading
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    monkeypatch.setattr(loop, "PULL_EVERY_SECONDS", 3600.0)
    codes = []
    def go():
        try: codes.append(loop.run_loop(argparse.Namespace(root=str(repo)), interval=0.05, passes=0))
        except Exception as err: codes.append(err)
    t = threading.Thread(target=go, daemon=True); t.start()
    time.sleep(0.5); assert t.is_alive()
    foreign_host(s)
    t.join(5)
    assert not t.is_alive() and len(codes) == 1 and "runs on desktop" in str(codes[0])

def test_loop_foreign_driver_host_error_follows_the_language(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys); foreign_host(s)
    monkeypatch.setattr(loop, "PULL_EVERY_SECONDS", 0.2)
    monkeypatch.setenv("NOD_LANG", "ru")
    code, _, err = driver_run(repo, "--interval", "0.1", "--passes", "3", capsys=capsys)
    assert code == 2 and "драйвер этого проекта работает на desktop" in err
    assert "драйвер этого проекта работает на desktop" in (s.root / "driver.log").read_text(encoding="utf-8")

def test_loop_with_empty_driver_host_is_unchanged(repo, capsys, monkeypatch, tmp_path):
    env_for_tests(monkeypatch, tmp_path); s = setup(repo, capsys)
    monkeypatch.setattr(loop, "PULL_EVERY_SECONDS", 3600.0)
    assert 'driver_host = ""' in (s.root / "harness.toml").read_text(encoding="utf-8")
    code, out, err = driver_run(repo, "--interval", "0.1", "--passes", "2", capsys=capsys)
    assert code == 0 and err == "" and out.count("pain:") == 1 and out.count("idle:") == 1 and "runs on" not in out
