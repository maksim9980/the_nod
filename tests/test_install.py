import json
from functools import partial
from pathlib import Path
from types import SimpleNamespace

from the_nod import harness, i18n
from the_nod.cli import main
from the_nod.driver import autostart
from the_nod.driver.autostart import JobStatus, Target
from the_nod.driver.autostart.windows import task_name
from the_nod.portability import doctor
from the_nod.portability import install as portability_install
from the_nod.portability.doctor import Machine
from the_nod.portability.install import copy_needed
from the_nod.store import Store

SETTINGS = '{\n  "permissions": {"allow": ["Bash(git *)"]},\n  "env": {"OTHER": "1"},\n  "hooks": {}\n}\n'


def test_copy_needed_file_and_directory(tmp_path):
    src = tmp_path / "src" / "s"; (src / "sub").mkdir(parents=True)
    (src / "sub" / "x.md").write_text("x\n", encoding="utf-8")
    dst = tmp_path / "home" / ".claude" / "skills" / "s"
    assert copy_needed(src, dst, dry_run=True) == f"would copy {dst}" and not dst.exists()
    assert copy_needed(src, dst, dry_run=False) == f"copied {dst}"
    assert (dst / "sub" / "x.md").read_text(encoding="utf-8") == "x\n"
    assert copy_needed(src, dst, dry_run=False) == "already in place"
    file_src = tmp_path / "src" / "a.md"; file_src.write_text("agent\n", encoding="utf-8")
    file_dst = tmp_path / "home" / ".claude" / "agents" / "a.md"
    assert copy_needed(file_src, file_dst, dry_run=False) == f"copied {file_dst}"
    assert file_dst.read_text(encoding="utf-8") == "agent\n"


# --- the CLI level: a fake machine, a fake schtasks ---


def windows_target(tmp_path) -> Target:
    return Target(platform="win32", home=tmp_path / "home", python="C:/Python313/pythonw.exe",
                  core=Path("C:/nod/the_nod/__main__.py"), uid=None, env={})


def make_machine(tmp_path, tasks: set, missing=()) -> Machine:
    def job_status(repo: Path) -> JobStatus:
        name = task_name(repo)
        return JobStatus(name in tasks, name in tasks, name)
    return Machine(home=tmp_path / "home", platform="win32",
                   which=lambda n: None if n in missing else "C:/bin/" + n,
                   has_module=lambda n: n == "the_nod", job_status=job_status,
                   python_in_path=lambda: None if "python" in missing else (3, 13))


def prepare(repo, capsys, tmp_path, monkeypatch, *, missing=(), schtasks_out="", skill=False, plugin=True):
    """A manifest with one agent (and a skill folder), the plugin in the registry, a fake machine and a fake schtasks."""
    main(["--root", str(repo), "init"])
    path = repo / ".nod" / "harness.toml"
    extra = 'skills = ["skills/s"]\n' if skill else ""
    path.write_text(path.read_text(encoding="utf-8") + '[needs]\nagents = [".claude/agents/a.md"]\n' + extra, encoding="utf-8")
    (repo / ".claude" / "agents").mkdir(parents=True)
    (repo / ".claude" / "agents" / "a.md").write_text("agent\n", encoding="utf-8")
    if skill:
        (repo / "skills" / "s").mkdir(parents=True)
        (repo / "skills" / "s" / "x.md").write_text("x\n", encoding="utf-8")
    capsys.readouterr()
    if plugin:
        registry = tmp_path / "home" / ".claude" / "plugins" / "installed_plugins.json"
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({"version": 2, "plugins": {"nod@nod": [{"scope": "user", "version": "0.1.0"}]}}), encoding="utf-8")
    tasks: set = set()
    calls: list = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        assert argv[0] == "schtasks", argv
        tasks.add(argv[argv.index("/TN") + 1])
        return SimpleNamespace(returncode=0, stdout=schtasks_out, stderr="")

    monkeypatch.setattr(autostart, "install", partial(autostart.install, target=windows_target(tmp_path), run=fake_run))
    m = make_machine(tmp_path, tasks, missing)
    monkeypatch.setattr(doctor, "machine", lambda: m)
    return calls, tasks


def run_install(repo, capsys, *extra):
    code = main(["--root", str(repo), "install", *extra])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_install_is_idempotent(repo, capsys, tmp_path, monkeypatch):
    calls, tasks = prepare(repo, capsys, tmp_path, monkeypatch)
    claude = tmp_path / "home" / ".claude"
    code, out, err = run_install(repo, capsys)
    target = claude / "agents" / "a.md"
    assert code == 0, (out, err)
    assert target.read_text(encoding="utf-8") == "agent\n" and task_name(repo) in tasks
    assert "agents/a.md →" in out and "job: driver autostart — done" in out
    mtime = target.stat().st_mtime_ns
    code, out, err = run_install(repo, capsys)
    assert out.splitlines()[0] == "nothing to do" and code == 0, (out, err)
    assert target.stat().st_mtime_ns == mtime and len(calls) == 1


def test_install_dry_run_prints_plan_and_changes_nothing(repo, capsys, tmp_path, monkeypatch):
    calls, _ = prepare(repo, capsys, tmp_path, monkeypatch)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "settings.json").write_text(SETTINGS, encoding="utf-8")
    code, out, err = run_install(repo, capsys, "--dry-run")
    assert "would do: driver autostart" in out and "would do: agents/a.md" in out
    assert (home / ".claude" / "settings.json").read_text(encoding="utf-8") == SETTINGS and calls == []
    assert not (home / ".claude" / "agents" / "a.md").exists() and code == 0


def test_install_manual_items_keep_exit_1(repo, capsys, tmp_path, monkeypatch):
    prepare(repo, capsys, tmp_path, monkeypatch, missing=("python", "claude"))
    code, out, err = run_install(repo, capsys)
    lines = out.splitlines()
    assert any(line.startswith("by hand: python ≥ 3.13:") for line in lines)
    assert any(line.startswith("by hand: claude:") for line in lines) and code == 1
    assert (tmp_path / "home" / ".claude" / "agents" / "a.md").exists()


def test_install_json_output(repo, capsys, tmp_path, monkeypatch):
    prepare(repo, capsys, tmp_path, monkeypatch)
    code = main(["--root", str(repo), "--json", "install"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["ok"] is True and out["done"] and all(c["ok"] for c in out["checks"])


def test_copy_needed_extra_files_are_not_deleted(tmp_path):
    src = tmp_path / "src" / "s"; src.mkdir(parents=True)
    (src / "x.md").write_text("x\n", encoding="utf-8")
    dst = tmp_path / "home" / ".claude" / "skills" / "s"; dst.mkdir(parents=True)
    (dst / "x.md").write_text("x\n", encoding="utf-8"); (dst / "old.md").write_text("old\n", encoding="utf-8")
    mtime = (dst / "x.md").stat().st_mtime_ns
    assert copy_needed(src, dst, dry_run=False) == f"extra files in {dst}, remove them by hand: old.md"
    assert (dst / "x.md").stat().st_mtime_ns == mtime and (dst / "old.md").exists()
    (src / "x.md").write_text("new\n", encoding="utf-8")
    assert copy_needed(src, dst, dry_run=False) == f"copied {dst}; extra files, remove them by hand: old.md"
    assert (dst / "x.md").read_text(encoding="utf-8") == "new\n" and (dst / "old.md").exists()


def skill_target(tmp_path, x_text: str) -> Path:
    dst = tmp_path / "home" / ".claude" / "skills" / "s"; dst.mkdir(parents=True)
    (dst / "x.md").write_text(x_text, encoding="utf-8"); (dst / "old.md").write_text("old\n", encoding="utf-8")
    return dst


def test_install_extra_files_only_writes_nothing_twice(repo, capsys, tmp_path, monkeypatch):
    prepare(repo, capsys, tmp_path, monkeypatch, skill=True)
    dst = skill_target(tmp_path, "x\n")
    mtimes = {p.name: p.stat().st_mtime_ns for p in dst.iterdir()}
    for _ in range(2):
        code, out, err = run_install(repo, capsys)
        assert f"extra files in {dst}, remove them by hand: old.md" in out and "extra files: old.md" in out and code == 1
        assert {p.name: p.stat().st_mtime_ns for p in dst.iterdir()} == mtimes


def test_install_changed_source_with_extra_copies_and_keeps_extra(repo, capsys, tmp_path, monkeypatch):
    prepare(repo, capsys, tmp_path, monkeypatch, skill=True)
    dst = skill_target(tmp_path, "old\n")
    code, out, err = run_install(repo, capsys)
    assert f"copied {dst}; extra files, remove them by hand: old.md" in out and code == 1
    assert (dst / "x.md").read_text(encoding="utf-8") == "x\n" and (dst / "old.md").exists()


def test_install_schtasks_output_goes_to_done(repo, capsys, tmp_path, monkeypatch):
    prepare(repo, capsys, tmp_path, monkeypatch, schtasks_out="SUCCESS: task created")
    code = main(["--root", str(repo), "--json", "install"])
    out = json.loads(capsys.readouterr().out)
    job = next(line for line in out["done"] if line.startswith("job:"))
    assert code == 0 and job.endswith("done: SUCCESS: task created")


def test_plan_has_no_pip_and_settings_steps(repo, capsys, tmp_path, monkeypatch):
    prepare(repo, capsys, tmp_path, monkeypatch, plugin=False)
    store = Store(repo / ".nod")
    needs = harness.load(store).needs
    m = doctor.machine()
    steps = portability_install.plan(doctor.checks(store, needs, m), needs=needs, m=m, store=store, dry_run=False)
    kinds = [step.kind for step in steps]
    assert kinds == ["copy", "job", "manual"] and "nod plugin" in steps[-1].what
    assert not hasattr(portability_install, "update_settings") and not hasattr(portability_install, "_pip")


def test_install_touches_no_settings(repo, capsys, tmp_path, monkeypatch):
    calls, _ = prepare(repo, capsys, tmp_path, monkeypatch)
    claude = tmp_path / "home" / ".claude"
    (claude / "settings.json").write_text(SETTINGS, encoding="utf-8")
    before = (claude / "settings.json").read_bytes()
    run_install(repo, capsys)
    assert (claude / "settings.json").read_bytes() == before and not list(claude.glob("settings.json.bak-*"))
    assert all(argv[0] == "schtasks" for argv in calls)


def test_install_in_russian(repo, capsys, tmp_path, monkeypatch):
    calls, tasks = prepare(repo, capsys, tmp_path, monkeypatch, schtasks_out="SUCCESS")
    monkeypatch.setenv("NOD_LANG", "ru")
    code, out, err = run_install(repo, capsys, "--dry-run")
    assert "сделал бы: автозапуск драйвера" in out and "сделал бы: agents/a.md" in out and code == 0
    code, out, err = run_install(repo, capsys)
    assert "job: автозапуск драйвера — готово: SUCCESS" in out and code == 0, (out, err)
    assert any(line.startswith("нужно") for line in out.splitlines())
    code, out, err = run_install(repo, capsys)
    assert out.splitlines()[0] == "ничего не нужно" and code == 0


def test_copy_needed_texts_in_russian(tmp_path):
    i18n.use("ru")
    src = tmp_path / "src" / "s"; src.mkdir(parents=True)
    (src / "x.md").write_text("x\n", encoding="utf-8")
    dst = tmp_path / "home" / ".claude" / "skills" / "s"
    assert copy_needed(src, dst, dry_run=True) == f"скопировал бы {dst}"
    assert copy_needed(src, dst, dry_run=False) == f"скопировано {dst}"
    assert copy_needed(src, dst, dry_run=False) == "уже есть"
    (dst / "old.md").write_text("old\n", encoding="utf-8")
    assert copy_needed(src, dst, dry_run=False) == f"лишние файлы в {dst}, убери руками: old.md"
    (src / "x.md").write_text("new\n", encoding="utf-8")
    assert copy_needed(src, dst, dry_run=False) == f"скопировано {dst}; лишние файлы, убери руками: old.md"


def test_install_job_failure_text(repo, capsys, tmp_path, monkeypatch):
    prepare(repo, capsys, tmp_path, monkeypatch)
    monkeypatch.setattr(autostart, "install", lambda root, dry_run=False: 5)
    assert main(["--root", str(repo), "install"]) == 2
    assert "error: driver autostart returned code 5" in capsys.readouterr().err
    monkeypatch.setenv("NOD_LANG", "ru")
    assert main(["--root", str(repo), "install"]) == 2
    assert "ошибка: автозапуск драйвера вернул код 5" in capsys.readouterr().err


def test_install_retries_a_unit_that_failed_to_enable(repo, capsys, tmp_path, monkeypatch):
    """A failed `enable --now` takes the unit away, so doctor says no and the next `nod install` tries again."""
    prepare(repo, capsys, tmp_path, monkeypatch)
    target = Target(platform="linux", home=tmp_path / "home", python="/usr/bin/python3",
                    core=Path("/opt/nod/the_nod/__main__.py"), uid=1000, env={"PATH": "/home/Jane Doe/.local/bin:/usr/bin"})
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        if argv[0] == "crontab":  # no crontab: read as bytes
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"no crontab")
        code = 1 if argv[:3] == ["systemctl", "--user", "enable"] else 0
        return SimpleNamespace(returncode=code, stdout="", stderr="Failed to enable unit" if code else "")

    monkeypatch.setattr(autostart, "install", partial(autostart.install, target=target, run=fake_run))
    m = Machine(home=tmp_path / "home", platform="linux", which=lambda n: "/usr/bin/" + n,
                has_module=lambda n: n == "the_nod", python_in_path=lambda: (3, 13),
                job_status=lambda root: autostart.status(root, target=target, run=fake_run))
    monkeypatch.setattr(doctor, "machine", lambda: m)
    for _ in range(2):
        assert main(["--root", str(repo), "install"]) == 2
        assert "error: driver autostart returned code 1" in capsys.readouterr().err
    assert sum(argv[:3] == ["systemctl", "--user", "enable"] for argv in calls) == 2
    assert not list((tmp_path / "home" / ".config" / "systemd" / "user").glob("*.service"))
    main(["--root", str(repo), "--json", "doctor"])
    job = next(c for c in json.loads(capsys.readouterr().out)["checks"] if c["name"] == "driver job")
    assert job["ok"] is False and job["detail"].startswith("job ")
