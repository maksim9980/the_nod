"""The probes of `python` and `python3` in PATH and the quotes around paths in the doctor fixes."""
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from the_nod.cli import main
from the_nod.portability import doctor
from the_nod.portability.doctor import Machine
from tests.test_doctor import by_name, doctor_json, fake_machine, init


def test_doctor_python_store_stub(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, python_in_path=lambda: None))
    init(repo, capsys)
    code, out = doctor_json(repo, capsys)
    check = by_name(out, "python ≥ 3.13")
    assert code == 1 and check["ok"] is False and "stub" in check["detail"] and check["auto"] is None


def test_doctor_python_ok_shows_version(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, python_in_path=lambda: (3, 14), which=lambda n: None))
    init(repo, capsys)
    _, out = doctor_json(repo, capsys)
    assert by_name(out, "python ≥ 3.13")["ok"] is True and by_name(out, "python ≥ 3.13")["detail"] == "3.14"


def probe_with(monkeypatch, result=None, error=None):
    """Replaces `subprocess.run` in doctor: the `python -c` probe does not run in tests."""
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((list(argv), kwargs))
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(doctor.subprocess, "run", fake_run)
    return calls


def test_python_in_path_parses_version(monkeypatch):
    calls = probe_with(monkeypatch, SimpleNamespace(returncode=0, stdout="3 13\n", stderr=""))
    assert doctor._python_in_path() == (3, 13)
    argv, kwargs = calls[0]
    assert argv[:2] == ["python", "-c"] and kwargs["timeout"] == 15 and kwargs["capture_output"] is True


def test_python_in_path_failures_are_none(monkeypatch):
    probe_with(monkeypatch, SimpleNamespace(returncode=9009, stdout="", stderr="Python was not found"))
    assert doctor._python_in_path() is None
    probe_with(monkeypatch, SimpleNamespace(returncode=0, stdout="Python was not found\n", stderr=""))
    assert doctor._python_in_path() is None
    probe_with(monkeypatch, error=OSError("no such file"))
    assert doctor._python_in_path() is None
    probe_with(monkeypatch, error=subprocess.TimeoutExpired("python", 15))
    assert doctor._python_in_path() is None


def test_quoted_path_with_space():
    plain = Path("C:/work/tidepool")
    assert doctor._quoted(plain) == str(plain)
    spaced = Path("C:/Users/Jane Doe/Nod")
    assert doctor._quoted(spaced) == f'"{spaced}"'


def test_doctor_python_store_stub_in_russian(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("NOD_LANG", "ru")
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, python_in_path=lambda: None))
    init(repo, capsys)
    _, out = doctor_json(repo, capsys)
    check = by_name(out, "python ≥ 3.13")
    assert "заглушка Microsoft Store" in check["detail"] and check["fix"].startswith("поставь Python ≥ 3.13")


# macOS and Linux: `python3` first, then `python`; the row `MCP server` asks for `python` by that exact name.
PYTHON_ROW = "python ≥ 3.13"
MCP_ROW = "MCP server"
POSIX = ["linux", "darwin"]


def posix_rows(repo, capsys, tmp_path, monkeypatch, platform="linux", **probes):
    """The python row and the MCP row of `nod doctor` on a fake machine of `platform`, with the exit code."""
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, platform=platform, **probes))
    init(repo, capsys)
    code, out = doctor_json(repo, capsys)
    return code, by_name(out, PYTHON_ROW), by_name(out, MCP_ROW)


@pytest.mark.parametrize("platform", POSIX)
def test_posix_python3_only_machine(repo, capsys, tmp_path, monkeypatch, platform):
    """Stock Ubuntu and macOS: python3 answers, python does not."""
    code, python, mcp = posix_rows(repo, capsys, tmp_path, monkeypatch, platform,
                                   python_in_path=lambda: None, python3_in_path=lambda: (3, 13))
    assert python == {"name": PYTHON_ROW, "ok": True, "detail": "3.13 (python3)", "fix": "—", "auto": None}
    assert mcp["ok"] is False and mcp["auto"] is None and mcp["detail"] == "no working python in PATH; the plugin starts its MCP server with it"
    assert mcp["fix"] == 'Debian/Ubuntu: sudo apt install python-is-python3; macOS: ln -s "$(command -v python3)" <folder in PATH>/python'
    assert code == 1


def test_posix_table_rows(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(
        tmp_path, platform="linux", python_in_path=lambda: None, python3_in_path=lambda: (3, 13)))
    init(repo, capsys)
    assert main(["--root", str(repo), "doctor"]) == 1
    out = capsys.readouterr().out
    assert re.search(r"python ≥ 3\.13\s+yes\s+—", out)
    assert re.search(r"MCP server\s+no \(no working python in PATH.*\)\s+Debian/Ubuntu: sudo apt install python-is-python3", out)


def test_posix_python3_is_tried_before_python(repo, capsys, tmp_path, monkeypatch):
    _, python, mcp = posix_rows(repo, capsys, tmp_path, monkeypatch,
                                python_in_path=lambda: (3, 13), python3_in_path=lambda: (3, 14))
    assert python["ok"] is True and python["detail"] == "3.14 (python3)"
    assert mcp == {"name": MCP_ROW, "ok": True, "detail": "3.13 (python)", "fix": "—", "auto": None}


def test_posix_python_answers_when_python3_is_too_old(repo, capsys, tmp_path, monkeypatch):
    _, python, _ = posix_rows(repo, capsys, tmp_path, monkeypatch,
                              python_in_path=lambda: (3, 13), python3_in_path=lambda: (3, 9))
    assert python["ok"] is True and python["detail"] == "3.13 (python)"


def test_posix_old_python3_only(repo, capsys, tmp_path, monkeypatch):
    code, python, _ = posix_rows(repo, capsys, tmp_path, monkeypatch,
                                 python_in_path=lambda: None, python3_in_path=lambda: (3, 11))
    assert code == 1 and python["ok"] is False and python["detail"] == "found 3.11 (python3)" and python["auto"] is None
    assert python["fix"] == "install Python ≥ 3.13 (python.org or your package manager) so that python3 is in PATH"


def test_posix_no_python_at_all(repo, capsys, tmp_path, monkeypatch):
    _, python, mcp = posix_rows(repo, capsys, tmp_path, monkeypatch,
                                python_in_path=lambda: None, python3_in_path=lambda: None)
    assert python["ok"] is False and python["detail"] == "python3 and python in PATH do not start"
    assert mcp["ok"] is False


def test_posix_python_too_old_for_the_mcp_server(repo, capsys, tmp_path, monkeypatch):
    """A `python` that is Python 2 starts, and the MCP server then fails: the row says what was found."""
    _, python, mcp = posix_rows(repo, capsys, tmp_path, monkeypatch,
                                python_in_path=lambda: (2, 7), python3_in_path=lambda: (3, 13))
    assert python["ok"] is True and python["detail"] == "3.13 (python3)"
    assert mcp["ok"] is False and mcp["detail"] == "found 2.7 (python)" and "python-is-python3" in mcp["fix"]


def test_windows_is_unchanged(repo, capsys, tmp_path, monkeypatch):
    """Windows: only `python` is probed, the texts are the old ones and there is no MCP row."""
    def never():
        raise AssertionError("python3 is not probed on Windows")

    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, python_in_path=lambda: (3, 14), python3_in_path=never))
    init(repo, capsys)
    _, out = doctor_json(repo, capsys)
    assert by_name(out, PYTHON_ROW) == {"name": PYTHON_ROW, "ok": True, "detail": "3.14", "fix": "—", "auto": None}
    assert MCP_ROW not in [c["name"] for c in out["checks"]]
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(tmp_path, python_in_path=lambda: None, python3_in_path=never))
    _, out = doctor_json(repo, capsys)
    stub = by_name(out, PYTHON_ROW)
    assert "Microsoft Store stub" in stub["detail"] and stub["fix"] == "install Python ≥ 3.13 from python.org and add python to PATH"


def test_posix_rows_in_russian(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("NOD_LANG", "ru")
    monkeypatch.setattr(doctor, "machine", lambda: fake_machine(
        tmp_path, platform="linux", python_in_path=lambda: None, python3_in_path=lambda: (3, 11)))
    init(repo, capsys)
    _, out = doctor_json(repo, capsys)
    python = by_name(out, PYTHON_ROW)
    assert python["detail"] == "найден 3.11 (python3)"
    assert python["fix"] == "поставь Python ≥ 3.13 (python.org или пакетный менеджер), чтобы python3 был в PATH"
    mcp = by_name(out, "MCP-сервер")
    assert mcp["detail"] == "в PATH нет работающего python; им плагин запускает MCP-сервер"
    assert "sudo apt install python-is-python3" in mcp["fix"] and "<папка из PATH>" in mcp["fix"]


def test_python3_in_path_runs_python3(monkeypatch):
    calls = probe_with(monkeypatch, SimpleNamespace(returncode=0, stdout="3 14\n", stderr=""))
    assert doctor._python3_in_path() == (3, 14)
    assert calls[0][0][:2] == ["python3", "-c"] and calls[0][1]["timeout"] == 15
    probe_with(monkeypatch, error=OSError("no such file"))
    assert doctor._python3_in_path() is None


def test_real_machine_probes_python3():
    assert doctor.machine().python3_in_path is doctor._python3_in_path


def test_machine_without_a_python3_probe_has_none():
    """A machine built the old way (no `python3_in_path`) has no python3 and never runs one."""
    m = Machine(home=Path("home"), platform="linux", which=lambda n: None, has_module=lambda n: False,
                job_status=lambda repo: None, python_in_path=lambda: (3, 13))
    assert m.python3_in_path() is None
