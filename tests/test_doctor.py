import json
import os
import re
import shutil
import sys
from pathlib import Path

from the_nod import i18n
from the_nod.cli import main
from the_nod.driver.autostart import JobStatus
from the_nod.portability import doctor
from the_nod.portability.doctor import Check, Machine
from tests.driver_helpers import REPO_ROOT

CYRILLIC = re.compile(r"[Ѐ-ӿ]")


MISSING_JOB = JobStatus(False, False, "Nod driver repo 0123abcd")


def _without_paths(text: str, *paths: Path | None) -> str:
    """`text` with the given machine paths cut out: a checkout or a temp folder may be named in any letters."""
    forms = {form for path in paths if path is not None
             for form in (str(path), path.as_posix(), str(path.resolve()), path.resolve().as_posix())}
    for form in sorted(forms, key=len, reverse=True):
        text = text.replace(form, "")
    return text


def fake_machine(tmp_path, *, platform="win32", python_in_path=lambda: (3, 13), python3_in_path=lambda: None, which=lambda n: "C:/bin/" + n, modules=("the_nod",), job: JobStatus = MISSING_JOB, env: dict | None = None):
    return Machine(home=tmp_path / "home", platform=platform, which=which, has_module=lambda n: n in modules, job_status=lambda repo: job, env=env or {}, python_in_path=python_in_path, python3_in_path=python3_in_path)


def settings(tmp_path, data) -> Path:
    path = tmp_path / "home" / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def installed(tmp_path, version="0.1.0", marketplace="nod", config: Path | None = None) -> Path:
    path = (config or tmp_path / "home" / ".claude") / "plugins" / "installed_plugins.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 2, "plugins": {f"nod@{marketplace}": [{"scope": "user", "installPath": "x", "version": version}]}}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def init(repo, capsys, needs: str = "") -> None:
    main(["--root", str(repo), "init"])
    if needs:
        path = repo / ".nod" / "harness.toml"
        path.write_text(path.read_text(encoding="utf-8") + "[needs]\n" + needs, encoding="utf-8")
    capsys.readouterr()


def doctor_json(repo, capsys):
    code = main(["--root", str(repo), "--json", "doctor"])
    return code, json.loads(capsys.readouterr().out)


def by_name(out, name):
    return next(c for c in out["checks"] if c["name"] == name)


def test_doctor_all_ok_exit_0(repo, capsys, tmp_path, monkeypatch):
    init(repo, capsys, 'agents = [".claude/agents/a.md"]\n')
    (repo / ".claude" / "agents").mkdir(parents=True)
    (repo / ".claude" / "agents" / "a.md").write_text("agent\n", encoding="utf-8")
    (tmp_path / "home" / ".claude" / "agents").mkdir(parents=True)
    shutil.copyfile(repo / ".claude" / "agents" / "a.md", tmp_path / "home" / ".claude" / "agents" / "a.md")
    installed(tmp_path)
    m = fake_machine(tmp_path, job=JobStatus(True, True, "C:/nod/the_nod/__main__.py"))
    monkeypatch.setattr(doctor, "machine", lambda: m)
    code, out = doctor_json(repo, capsys)
    assert code == 0 and out["ok"] is True and all(c["ok"] for c in out["checks"])
    names = [c["name"] for c in out["checks"]]
    assert names == ["python ≥ 3.13", "claude", "nod plugin", "driver job", "agents/a.md"]
    assert by_name(out, "nod plugin")["detail"] == "0.1.0 from nod"
    assert main(["--root", str(repo), "doctor"]) == 0
    table_text = capsys.readouterr().out
    assert table_text.splitlines()[0].split() == ["need", "have", "fix"]


def test_doctor_missing_python(repo, capsys, tmp_path, monkeypatch):
    m = fake_machine(tmp_path, python_in_path=lambda: None, which=lambda n: None, modules=())
    monkeypatch.setattr(doctor, "machine", lambda: m)
    main(["--root", str(repo), "init"]); capsys.readouterr()
    code = main(["--root", str(repo), "doctor"])
    out = capsys.readouterr().out
    assert code == 1 and re.search(r"python ≥ 3\.13\s+no", out) and "pip install -e" not in out


def test_doctor_old_python_detail(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, python_in_path=lambda: (3, 11)))
    init(repo, capsys)
    code, out = doctor_json(repo, capsys)
    check = by_name(out, "python ≥ 3.13")
    assert code == 1 and check["ok"] is False and check["detail"] == "found 3.11" and check["auto"] is None
    assert check["fix"] == "install Python ≥ 3.13 from python.org and add python to PATH"


def test_doctor_nod_as_python_module(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, which=lambda n: "C:/py" if n == "python" else None))
    init(repo, capsys, 'nod = "python -m the_nod"\nclaude = ""\n')
    _, out = doctor_json(repo, capsys)
    assert by_name(out, "nod")["ok"] is True and "claude" not in [c["name"] for c in out["checks"]]


def test_doctor_job_checked_off_windows_too(repo, capsys, tmp_path, monkeypatch):
    m = fake_machine(tmp_path, platform="linux", job=JobStatus(False, False, "nod-driver-0123abcd.service"))
    monkeypatch.setattr(doctor, "machine", lambda: m)
    init(repo, capsys)
    _, out = doctor_json(repo, capsys)
    assert by_name(out, "driver job") == {"name": "driver job", "ok": False,
                                          "detail": 'job "nod-driver-0123abcd.service" not found',
                                          "fix": "nod driver install", "auto": "job"}
    main(["--root", str(repo), "doctor"])
    assert re.search(r'driver job\s+no \(job "nod-driver-0123abcd\.service" not found\)\s+nod driver install',
                     capsys.readouterr().out)


def test_doctor_job_pointing_at_another_core(repo, capsys, tmp_path, monkeypatch):
    old = "/Users/Jane Doe/old/nod/the_nod/__main__.py"
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, platform="darwin", job=JobStatus(True, False, old)))
    init(repo, capsys)
    _, out = doctor_json(repo, capsys)
    job = by_name(out, "driver job")
    assert job["ok"] is False and job["detail"] == f"points to {old}" and job["fix"] == "nod driver install"
    assert job["auto"] == "job"
    monkeypatch.setenv("NOD_LANG", "ru")
    _, out = doctor_json(repo, capsys)
    assert by_name(out, "задача драйвера")["detail"] == f"указывает на {old}"


def test_doctor_job_missing_on_windows(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path))
    init(repo, capsys)
    _, out = doctor_json(repo, capsys)
    job = by_name(out, "driver job")
    assert job["ok"] is False and job["fix"] == "nod driver install" and job["auto"] == "job"


def test_doctor_no_jobs_no_job_check(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path))
    init(repo, capsys, "jobs = []\n")
    _, out = doctor_json(repo, capsys)
    assert "driver job" not in [c["name"] for c in out["checks"]]


def test_doctor_copy_checks(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path))
    init(repo, capsys, 'agents = [".claude/agents/a.md", ".claude/agents/none.md"]\n')
    (repo / ".claude" / "agents").mkdir(parents=True)
    (repo / ".claude" / "agents" / "a.md").write_text("agent\n", encoding="utf-8")
    _, out = doctor_json(repo, capsys)
    agent = by_name(out, "agents/a.md")
    assert agent["ok"] is False and agent["fix"] == "nod install" and agent["auto"] == "copy" and agent["detail"] == "not in ~/.claude"
    none = by_name(out, "agents/none.md")
    assert none["ok"] is False and none["detail"] == "no source in the repo" and none["auto"] is None
    target = tmp_path / "home" / ".claude" / "agents" / "a.md"
    target.parent.mkdir(parents=True)
    target.write_text("other\n", encoding="utf-8")
    _, out = doctor_json(repo, capsys)
    assert by_name(out, "agents/a.md")["detail"] == "differs"


def test_doctor_skill_directory_compared(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path))
    init(repo, capsys, 'skills = ["skills/s"]\n')
    (repo / "skills" / "s" / "sub").mkdir(parents=True)
    (repo / "skills" / "s" / "SKILL.md").write_text("skill\n", encoding="utf-8")
    (repo / "skills" / "s" / "sub" / "x.txt").write_text("x\n", encoding="utf-8")
    shutil.copytree(repo / "skills" / "s", tmp_path / "home" / ".claude" / "skills" / "s")
    _, out = doctor_json(repo, capsys)
    assert by_name(out, "skills/s") == {"name": "skills/s", "ok": True, "detail": "matches", "fix": "—", "auto": None}
    (tmp_path / "home" / ".claude" / "skills" / "s" / "extra.txt").write_text("extra", encoding="utf-8")
    _, out = doctor_json(repo, capsys)
    check = by_name(out, "skills/s")
    assert check["detail"] == "extra files: extra.txt" and check["auto"] == "copy"


def test_doctor_bad_manifest_is_cli_error(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path))
    init(repo, capsys, 'python = "3"\n')
    assert main(["--root", str(repo), "doctor"]) == 2
    assert "python" in capsys.readouterr().err


def test_harness_error_reexported():
    from the_nod import errors, harness
    assert harness.HarnessError is errors.HarnessError and issubclass(errors.HarnessError, ValueError)


def test_table_format():
    text = doctor.table([Check("python ≥ 3.13", True, "", "install", None),
                         Check("driver job", True, "exists", "—", None),
                         Check("nod", False, "not in PATH", "pip install -e D:/x", None)])
    lines = text.splitlines()
    assert lines[0] == "need" + " " * 11 + "have" + " " * 14 + "fix"
    assert lines[1] == "python ≥ 3.13" + " " * 2 + "yes" + " " * 15 + "—"
    assert lines[2] == "driver job" + " " * 5 + "yes" + " " * 15 + "—"  # a passed check hides its detail
    assert lines[3] == "nod" + " " * 12 + "no (not in PATH)" + " " * 2 + "pip install -e D:/x"
    assert doctor.all_ok([]) is True and doctor.all_ok([Check("a", False, "", "", None)]) is False


def test_table_format_in_russian():
    i18n.use("ru")
    text = doctor.table([Check("python ≥ 3.13", True, "", "поставь", None),
                         Check("задача драйвера", True, "есть", "—", None),
                         Check("nod", False, "нет в PATH", "pip install -e D:/x", None)])
    lines = text.splitlines()
    assert lines[0] == "нужно" + " " * 12 + "есть" + " " * 14 + "чем лечится"
    assert lines[1] == "python ≥ 3.13" + " " * 4 + "да" + " " * 16 + "—"
    assert lines[2] == "задача драйвера  да" + " " * 16 + "—"
    assert lines[3] == "nod" + " " * 14 + "нет (нет в PATH)" + " " * 2 + "pip install -e D:/x"


def test_doctor_table_both_languages(repo, capsys, tmp_path, monkeypatch):
    """The same machine, both languages: row names, the answers and the column heads follow NOD_LANG."""
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, python_in_path=lambda: None, which=lambda n: None))
    init(repo, capsys)
    assert main(["--root", str(repo), "doctor"]) == 1
    english = capsys.readouterr().out
    assert not CYRILLIC.search(_without_paths(english, doctor.plugin_root(), tmp_path))
    assert english.splitlines()[0].split() == ["need", "have", "fix"]
    assert re.search(r"nod plugin\s+no \(not installed\)", english) and re.search(r"driver job\s+no \(job .* not found\)", english)
    assert re.search(r"claude\s+no \(not in PATH\)", english)
    monkeypatch.setenv("NOD_LANG", "ru")
    assert main(["--root", str(repo), "doctor"]) == 1
    russian = capsys.readouterr().out
    assert russian.splitlines()[0].split() == ["нужно", "есть", "чем", "лечится"]
    assert re.search(r"плагин nod\s+нет \(не установлен\)", russian) and re.search(r"задача драйвера\s+нет \(задача .* не найдена\)", russian)
    assert re.search(r"claude\s+нет \(не в PATH\)", russian)
    assert "python ≥ 3.13" in russian and "claude plugin marketplace add" in russian and "; claude plugin install nod@nod" in russian


def test_english_doctor_check_ignores_a_cyrillic_checkout(repo, capsys, tmp_path, monkeypatch):
    """The fix column names the checkout; a folder name in any letters is not Russian text of Nod."""
    checkout = tmp_path / "Проекты" / "the_nod"
    monkeypatch.setattr(doctor, "plugin_root", lambda: checkout)
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, python_in_path=lambda: None, which=lambda n: None))
    init(repo, capsys)
    assert main(["--root", str(repo), "doctor"]) == 1
    english = capsys.readouterr().out
    assert CYRILLIC.search(english)  # the path is in the output
    assert not CYRILLIC.search(_without_paths(english, checkout, tmp_path))


def test_doctor_json_texts_follow_the_language(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, python_in_path=lambda: (3, 11)))
    init(repo, capsys)
    _, out = doctor_json(repo, capsys)
    assert by_name(out, "python ≥ 3.13")["detail"] == "found 3.11"
    monkeypatch.setenv("NOD_LANG", "ru")
    _, out = doctor_json(repo, capsys)
    check = by_name(out, "python ≥ 3.13")
    assert check["detail"] == "найден 3.11" and check["fix"] == "поставь Python ≥ 3.13 с python.org и включи python в PATH"
    assert [c["name"] for c in out["checks"]] == ["python ≥ 3.13", "claude", "плагин nod", "задача драйвера"]


def test_doctor_plugin_double_load_in_russian(repo, capsys, tmp_path, monkeypatch):
    folder = str(plugin_folder(tmp_path))
    monkeypatch.setenv("NOD_LANG", "ru")
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, env={"CLAUDE_CODE_PLUGIN_DIRS": folder}))
    settings(tmp_path, {"env": {"CLAUDE_CODE_PLUGIN_DIRS": folder}})
    installed(tmp_path)
    init(repo, capsys)
    _, out = doctor_json(repo, capsys)
    plugin = by_name(out, "плагин nod")
    assert plugin["detail"] == "установлен и ещё в CLAUDE_CODE_PLUGIN_DIRS (settings.json, окружение) — двойная загрузка"
    assert plugin["fix"] == "убери путь из env в ~/.claude/settings.json: плагин грузится сам"


def test_real_machine_fields():
    m = doctor.machine()
    assert m.platform == sys.platform and m.home == Path.home() and m.python_in_path is doctor._python_in_path
    assert m.job_status is doctor._job_status
    assert m.has_module("the_nod") is True and m.has_module("no_such_module") is False


def test_plugin_root_is_repo():
    assert doctor.plugin_root() == REPO_ROOT


def test_read_json(tmp_path):
    path = tmp_path / "x.json"
    assert doctor.read_json(path) == ({}, "")
    path.write_text('{"a": 1}', encoding="utf-8")
    assert doctor.read_json(path) == ({"a": 1}, "")
    path.write_text("[1]", encoding="utf-8")
    assert doctor.read_json(path) == (None, f"{path}: expected an object")
    path.write_text('{\n"a": ,\n}', encoding="utf-8")
    data, error = doctor.read_json(path)
    assert data is None and f"{path} is unreadable" in error and error.endswith("(line 2)")


def test_installed_plugins(tmp_path):
    config = tmp_path / "home" / ".claude"
    assert doctor.installed_plugins(config) == []
    installed(tmp_path, version="1.0", marketplace="a/b")
    assert doctor.installed_plugins(config) == [("a/b", "1.0")]
    path = installed(tmp_path)
    path.write_text(json.dumps({"plugins": {"other@x": [{"version": "1"}], "nod@m": [{}], "nod@e": []}}), encoding="utf-8")
    assert doctor.installed_plugins(config) == [("m", "?")]
    path.write_text(json.dumps({"plugins": []}), encoding="utf-8")
    assert doctor.installed_plugins(config) == []


def test_dir_sources_from_env_and_settings(tmp_path):
    m = fake_machine(tmp_path, env={"CLAUDE_CODE_PLUGIN_DIRS": f"a{os.pathsep}{os.pathsep} {os.pathsep}b"})
    env_pairs = [("env", "a"), ("env", "b")]
    assert doctor._dir_sources(m) == env_pairs
    settings(tmp_path, {"env": {"CLAUDE_CODE_PLUGIN_DIRS": "c"}})
    assert doctor._dir_sources(m) == [("settings.json", "c"), *env_pairs]
    settings(tmp_path, {"env": "x"})
    assert doctor._dir_sources(m) == env_pairs
    (tmp_path / "home" / ".claude" / "settings.json").write_text("{ oops", encoding="utf-8")
    assert doctor._dir_sources(m) == env_pairs
    assert not hasattr(doctor, "plugin_dirs")


def test_config_dir_env_or_home(tmp_path):
    home_config = tmp_path / "home" / ".claude"
    assert doctor.config_dir(fake_machine(tmp_path)) == home_config
    assert doctor.config_dir(fake_machine(tmp_path, env={"CLAUDE_CONFIG_DIR": "  "})) == home_config
    assert doctor.config_dir(fake_machine(tmp_path, env={"CLAUDE_CONFIG_DIR": str(tmp_path / "cfg")})) == tmp_path / "cfg"


def test_doctor_reads_claude_config_dir(repo, capsys, tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, env={"CLAUDE_CONFIG_DIR": str(cfg)}))
    installed(tmp_path, version="0.2.1", config=cfg)
    init(repo, capsys, 'agents = [".claude/agents/a.md"]\n')
    (repo / ".claude" / "agents").mkdir(parents=True)
    (repo / ".claude" / "agents" / "a.md").write_text("agent\n", encoding="utf-8")
    (cfg / "agents").mkdir(parents=True)
    shutil.copyfile(repo / ".claude" / "agents" / "a.md", cfg / "agents" / "a.md")
    _, out = doctor_json(repo, capsys)
    plugin = {"name": "nod plugin", "ok": True, "detail": "0.2.1 from nod", "fix": "—", "auto": None}
    assert by_name(out, "nod plugin") == plugin and by_name(out, "agents/a.md")["ok"] is True


def test_doctor_plugin_not_installed(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path))
    init(repo, capsys)
    code, out = doctor_json(repo, capsys)
    p = by_name(out, "nod plugin")
    assert code == 1 and p["ok"] is False and p["detail"] == "not installed" and p["auto"] is None
    assert p["fix"] == f"claude plugin marketplace add {doctor.plugin_root()}; claude plugin install nod@nod"


def test_doctor_plugin_not_installed_without_root(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "plugin_root", lambda: None)
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path))
    init(repo, capsys)
    _, out = doctor_json(repo, capsys)
    assert by_name(out, "nod plugin")["fix"] == "claude plugin marketplace add <Nod folder or repo>; claude plugin install nod@nod"


def test_doctor_plugin_installed_any_version(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path))
    init(repo, capsys)
    installed(tmp_path, version="9.9.9-dev", marketplace="someone/nod")
    _, out = doctor_json(repo, capsys)
    assert by_name(out, "nod plugin") == {"name": "nod plugin", "ok": True, "detail": "9.9.9-dev from someone/nod", "fix": "—", "auto": None}


def test_doctor_plugin_via_plugin_dirs(repo, capsys, tmp_path, monkeypatch):
    root = str(doctor.plugin_root())
    m = fake_machine(tmp_path, env={"CLAUDE_CODE_PLUGIN_DIRS": "D:\\other" + os.pathsep + root})
    monkeypatch.setattr(doctor, "machine", lambda: m)
    init(repo, capsys)
    _, out = doctor_json(repo, capsys)
    assert by_name(out, "nod plugin")["ok"] is True and by_name(out, "nod plugin")["detail"] == "via CLAUDE_CODE_PLUGIN_DIRS"


def plugin_folder(tmp_path, name="nod") -> Path:
    folder = tmp_path / "plug"
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    (folder / "mod" / "nod-pane").mkdir(parents=True)
    return folder


def test_doctor_plugin_double_load(repo, capsys, tmp_path, monkeypatch):
    mod = str(plugin_folder(tmp_path) / "mod" / "nod-pane")
    mod = mod.upper() if sys.platform == "win32" else mod  # case does not matter on Windows
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path))
    settings(tmp_path, {"env": {"CLAUDE_CODE_PLUGIN_DIRS": mod}})
    installed(tmp_path)
    init(repo, capsys)
    code, out = doctor_json(repo, capsys)
    p = by_name(out, "nod plugin")
    assert code == 1 and p["ok"] is False and p["fix"] == "remove the path from env in ~/.claude/settings.json: the plugin loads by itself" and p["auto"] is None
    assert p["detail"] == "installed and also in CLAUDE_CODE_PLUGIN_DIRS (settings.json) — double load"


def test_doctor_plugin_double_load_sources(repo, capsys, tmp_path, monkeypatch):
    folder = str(plugin_folder(tmp_path))
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, env={"CLAUDE_CODE_PLUGIN_DIRS": folder}))
    installed(tmp_path)
    init(repo, capsys)
    _, out = doctor_json(repo, capsys)
    assert "(environment) — double" in by_name(out, "nod plugin")["detail"]
    settings(tmp_path, {"env": {"CLAUDE_CODE_PLUGIN_DIRS": folder}})
    _, out = doctor_json(repo, capsys)
    assert "(settings.json, environment) — double" in by_name(out, "nod plugin")["detail"]


def test_doctor_plugin_dirs_foreign_manifest_is_not_ours(repo, capsys, tmp_path, monkeypatch):
    folder = str(plugin_folder(tmp_path, name="other"))
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, env={"CLAUDE_CODE_PLUGIN_DIRS": folder}))
    installed(tmp_path)
    init(repo, capsys)
    code, out = doctor_json(repo, capsys)
    p = by_name(out, "nod plugin")
    assert p["ok"] is True and p["detail"] == "0.1.0 from nod"


def test_is_ours_manifest_levels_and_broken(tmp_path):
    folder = plugin_folder(tmp_path)
    assert doctor.is_ours(folder, None) and doctor.is_ours(folder / "mod" / "nod-pane", None)
    assert not doctor.is_ours(tmp_path / "elsewhere", None)
    (folder / ".claude-plugin" / "plugin.json").write_text("{ oops", encoding="utf-8")
    assert not doctor.is_ours(folder, None)


def test_doctor_plugin_installed_twice(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path))
    path = installed(tmp_path, marketplace="a")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["plugins"]["nod@b"] = [{"scope": "user", "version": "0.1.0"}]
    path.write_text(json.dumps(data), encoding="utf-8")
    init(repo, capsys)
    code, out = doctor_json(repo, capsys)
    p = by_name(out, "nod plugin")
    assert code == 1 and p["ok"] is False and p["auto"] is None
    assert p["detail"] == "installed twice: a, b — double load"
    assert p["fix"] == "remove the extra one: claude plugin uninstall nod@b"


def test_doctor_nod_only_when_set(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, which=lambda n: None))
    init(repo, capsys)
    _, out = doctor_json(repo, capsys)
    assert "nod" not in [c["name"] for c in out["checks"]]
    manifest = repo / ".nod" / "harness.toml"
    manifest.write_text(manifest.read_text(encoding="utf-8") + '[needs]\nnod = "nod"\n', encoding="utf-8")
    _, out = doctor_json(repo, capsys)
    nod = by_name(out, "nod")
    assert nod["ok"] is False and nod["fix"] == f"pip install -e {doctor.plugin_root()}" and nod["auto"] is None


def test_doctor_broken_registry_is_not_installed(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path))
    path = tmp_path / "home" / ".claude" / "plugins" / "installed_plugins.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ oops", encoding="utf-8")
    init(repo, capsys)
    _, out = doctor_json(repo, capsys)
    assert by_name(out, "nod plugin")["detail"] == "not installed"
