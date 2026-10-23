"""The `nod` wrapper for the driver's agents: the files, the quoting, a real run, the `PATH` the agent gets."""
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

import the_nod
from the_nod.driver import files, shim
from the_nod.store import Store
from tests.driver_helpers import add_card, driver_run, env_for_tests, setup

WINDOWS = sys.platform == "win32"
PYTHON = "C:\\Users\\Jane Doe\\Python313\\python.exe"
CORE = "C:\\Users\\Jane Doe\\Application Support\\nod\\the_nod\\__main__.py"


@pytest.fixture(params=["Jane Doe", "Jane Doe \u0418\u0432\u0430\u043d"], ids=["spaces", "spaces-and-cyrillic"])
def folder(request) -> str:
    """The user folder of the wrapper: a space, and a non-ASCII name next to it (a Cyrillic first name)."""
    return request.param


def oem_holds(text: str) -> bool:
    """Whether cmd can be given `text` in a batch file: always off Windows, else if the OEM code page encodes it."""
    try:
        text.encode(shim.CMD_ENCODING if WINDOWS else "utf-8")
    except UnicodeEncodeError:
        return False
    return True


def spaced_core(home: Path) -> Path:
    """A copy of the core package under a folder with a space: `-P` and `__main__.py` must find it there."""
    target = home / "Application Support" / "the_nod"
    shutil.copytree(Path(the_nod.__file__).parent, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target / "__main__.py"


def run_in_shell(argv: list[str], bin_dir: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": shim.env_path(bin_dir, os.environ.get("PATH", ""))}
    return subprocess.run(argv, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)


def git_bash() -> str | None:
    """Git Bash on Windows (not the WSL launcher in System32), `bash` elsewhere; None if absent."""
    if not WINDOWS:
        return shutil.which("bash")
    git = shutil.which("git")
    if git is None:
        return None
    for folder in Path(git).resolve().parents[:3]:
        for rel in ("bin/bash.exe", "usr/bin/bash.exe"):
            if (folder / rel).is_file():
                return str(folder / rel)
    return None


def test_shim_files_per_platform(tmp_path):
    win = shim.write(tmp_path / "win", PYTHON, PureWindowsPath(CORE), platform="win32")
    assert [p.name for p in win] == ["nod", "nod.cmd"]
    assert win[0].read_bytes() == (
        b"#!/bin/sh\n"
        b"exec 'C:/Users/Jane Doe/Python313/python.exe' "
        b"-P 'C:/Users/Jane Doe/Application Support/nod/the_nod/__main__.py' \"$@\"\n")
    assert win[1].read_bytes() == (
        b'@"C:\\Users\\Jane Doe\\Python313\\python.exe" '
        b'-P "C:\\Users\\Jane Doe\\Application Support\\nod\\the_nod\\__main__.py" %*\r\n')
    posix = shim.write(tmp_path / "posix", "/usr/bin/python3", PurePosixPath("/opt/nod/the_nod/__main__.py"), platform="linux")
    assert [p.name for p in posix] == ["nod"]
    assert posix[0].read_bytes() == b"#!/bin/sh\nexec /usr/bin/python3 -P /opt/nod/the_nod/__main__.py \"$@\"\n"
    assert sorted(p.name for p in (tmp_path / "posix").iterdir()) == ["nod"]  # no stray temporary files
    if not WINDOWS:
        assert posix[0].stat().st_mode & 0o777 == 0o755


def test_shim_script_quotes_every_path(tmp_path):
    """The `exec` line splits back into the exact argv, whatever the paths hold."""
    python, core = "/opt/Jane's Python/bin/python3", "/Users/Jane Doe/Library/Application Support/nod/the_nod/__main__.py"
    script = shim.write(tmp_path, python, PurePosixPath(core), platform="darwin")[0].read_text(encoding="utf-8")
    assert shlex.split(script.splitlines()[1]) == ["exec", python, "-P", core, "$@"]


def test_shim_is_rewritten_in_place(tmp_path):
    shim.write(tmp_path, "/usr/bin/python3", PurePosixPath("/opt/a/__main__.py"), platform="linux")
    again = shim.write(tmp_path, "/usr/bin/python3", PurePosixPath("/opt/b/__main__.py"), platform="linux")
    assert b"/opt/b/__main__.py" in again[0].read_bytes() and b"/opt/a" not in again[0].read_bytes()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["nod"]


def test_cmd_shim_uses_the_console_code_page(tmp_path, monkeypatch):
    """A non-ASCII user name must reach cmd in its code page; a percent sign is doubled."""
    user = "\u0418\u0432\u0430\u043d"  # a Cyrillic first name: the home folder `C:\Users\<name>`
    python = rf"C:\Users\{user}\100%\python.exe"
    monkeypatch.setattr(shim, "CMD_ENCODING", "cp866")
    path = shim.write(tmp_path, python, PureWindowsPath(CORE), platform="win32")[1]
    expected = rf'@"C:\Users\{user}\100%%\python.exe" -P "{CORE}" %*' + "\r\n"
    assert path.read_bytes() == expected.encode("cp866")
    monkeypatch.setattr(shim, "CMD_ENCODING", "ascii")  # a path the code page cannot hold: utf-8 stays
    path = shim.write(tmp_path, python, PureWindowsPath(CORE), platform="win32")[1]
    assert user in path.read_text(encoding="utf-8")


def test_bin_dir_is_in_the_driver_folder(repo):
    store = Store(repo / ".nod")
    assert shim.bin_dir(store) == (repo / ".nod" / "driver" / files.BIN_DIR).absolute()
    assert shim.bin_dir(store).name == "bin"


def test_env_path_puts_bin_first(tmp_path):
    folder = tmp_path / "Jane Doe" / "bin"
    assert shim.env_path(folder, os.pathsep.join(["x", "y"])) == os.pathsep.join([str(folder), "x", "y"])


def test_env_path_keeps_the_system_default_for_an_empty_path(tmp_path, monkeypatch):
    """An unset `PATH` must not leave the agent with the wrapper folder alone: `git`, `claude` would vanish."""
    folder = tmp_path / "bin"
    monkeypatch.setattr(shim, "DEFAULT_PATH", "/usr/bin" + os.pathsep + "/bin")
    assert shim.env_path(folder, "") == os.pathsep.join([str(folder), "/usr/bin", "/bin"])
    assert shim.env_path(folder, "/opt/tools") == os.pathsep.join([str(folder), "/opt/tools"])  # a set PATH wins
    monkeypatch.setattr(shim, "DEFAULT_PATH", "")  # no default (Windows): the wrapper folder alone
    assert shim.env_path(folder, "") == str(folder)


@pytest.mark.skipif(WINDOWS, reason="a POSIX default path")
def test_default_path_is_the_posix_default():
    assert shim.DEFAULT_PATH == os.defpath


def test_agent_env_without_path_in_the_environment(repo, monkeypatch):
    monkeypatch.delenv("PATH", raising=False)
    monkeypatch.setattr(shim, "DEFAULT_PATH", "/usr/bin" + os.pathsep + "/bin")
    path = shim.agent_env(Store(repo / ".nod"))["PATH"]
    assert path == os.pathsep.join([str(shim.bin_dir(Store(repo / ".nod"))), "/usr/bin", "/bin"])


def test_shim_gets_its_mode_before_it_replaces_the_old_file(tmp_path, monkeypatch):
    """`mkstemp` makes a 0o600 file: the mode is set on it before `os.replace`, so the wrapper is never seen with 0o600."""
    events: list[str] = []
    real_chmod, real_replace = os.chmod, os.replace
    monkeypatch.setattr(os, "chmod", lambda p, *a, **k: (events.append(f"chmod {Path(p).name}"), real_chmod(p, *a, **k))[1])
    monkeypatch.setattr(os, "replace", lambda s, d: (events.append(f"replace {Path(d).name}"), real_replace(s, d))[1])
    shim.write(tmp_path, "/usr/bin/python3", PurePosixPath("/opt/nod/the_nod/__main__.py"), platform="linux")
    chmod, replace = events
    assert chmod.startswith("chmod nod.") and chmod.endswith(".tmp") and replace == "replace nod"
    if not WINDOWS:
        assert (tmp_path / "nod").stat().st_mode & 0o777 == 0o755


def test_agent_python_prefers_console_python(tmp_path, monkeypatch):
    scripts = tmp_path / "Python 313"
    scripts.mkdir()
    windowed = scripts / "pythonw.exe"
    monkeypatch.setattr(sys, "executable", str(windowed))
    assert shim.agent_python() == str(windowed)  # no console twin: nothing better exists
    (scripts / "python.exe").write_bytes(b"")
    assert shim.agent_python() == str(scripts / "python.exe")
    ordinary = scripts / "python3"
    monkeypatch.setattr(sys, "executable", str(ordinary))
    assert shim.agent_python() == str(ordinary)


def test_core_path_is_the_package_entry():
    assert shim.core_path() == Path(the_nod.__file__).resolve().with_name("__main__.py")
    assert shim.core_path().is_file()


def test_shim_runs_with_spaces(tmp_path, folder):
    if not oem_holds(folder):
        pytest.skip("the OEM code page of this machine cannot hold the folder name")
    home = tmp_path / folder
    bin_dir = home / "bin"
    shim.write(bin_dir, sys.executable, spaced_core(home))
    argv = ["cmd", "/c", "nod", "--help"] if WINDOWS else ["sh", "-c", "nod --help"]
    done = run_in_shell(argv, bin_dir)
    assert done.returncode == 0, done.stderr
    assert "usage: nod" in done.stdout


def test_shim_keeps_the_exit_code(tmp_path):
    home = tmp_path / "Jane Doe"
    bin_dir = home / "bin"
    shim.write(bin_dir, sys.executable, spaced_core(home))
    argv = ["cmd", "/c", "nod", "no-such-command"] if WINDOWS else ["sh", "-c", "nod no-such-command"]
    assert run_in_shell(argv, bin_dir).returncode == 2


@pytest.mark.skipif(git_bash() is None, reason="no bash")
def test_shim_runs_under_bash_on_windows(tmp_path, folder):
    """The Claude Code Bash tool runs Git Bash on Windows: the extension-less `nod` must work there."""
    home = tmp_path / folder
    bin_dir = home / "bin"
    shim.write(bin_dir, sys.executable, spaced_core(home))
    done = run_in_shell([git_bash(), "-c", "nod --help"], bin_dir)
    assert done.returncode == 0, done.stderr
    assert "usage: nod" in done.stdout


def test_driver_passes_path_to_agent(repo, capsys, tmp_path, monkeypatch):
    env_for_tests(monkeypatch, tmp_path)
    store = setup(repo, capsys, brief="path")
    cid = add_card(repo, capsys)
    driver_run(repo, "once", capsys=capsys)
    printed = files.output_paths(store, cid, "brief")[0].read_text(encoding="utf-8").strip()
    first = printed.split(os.pathsep)[0]
    assert Path(first).resolve() == (repo / ".nod" / "driver" / "bin").resolve()
    assert printed.endswith(os.pathsep + os.environ["PATH"])  # the rest of the PATH is untouched
    assert (Path(first) / "nod").is_file()


def test_agent_command_finds_nod(repo, capsys, tmp_path, monkeypatch):
    """An agent that types `nod --help` into a shell reaches the core, with no pip anywhere."""
    env_for_tests(monkeypatch, tmp_path)
    store = setup(repo, capsys, brief="nod")
    cid = add_card(repo, capsys)
    driver_run(repo, "once", capsys=capsys)
    assert "usage: nod" in files.output_paths(store, cid, "brief")[0].read_text(encoding="utf-8")


def test_agent_env_restores_an_edited_wrapper(repo):
    """The wrapper is rewritten before every command, so a copy an agent edited does not run in the next one."""
    store = Store(repo / ".nod")
    shim.agent_env(store)
    folder = shim.bin_dir(store)
    good = {path.name: path.read_bytes() for path in folder.iterdir()}
    for name in good:
        (folder / name).write_text("echo pwned\n", encoding="utf-8")
    shim.agent_env(store)
    assert {path.name: path.read_bytes() for path in folder.iterdir()} == good


def test_agent_env_clears_strangers_from_the_wrapper_folder(repo):
    """The folder stands first in the agent's PATH: a `git` an agent dropped there would run in the next command."""
    store = Store(repo / ".nod")
    shim.agent_env(store)
    folder = shim.bin_dir(store)
    wrappers = sorted(path.name for path in folder.iterdir())
    for name in ("git", "git.cmd", "claude.exe", "nod.bat", "nod.1234.tmp"):
        (folder / name).write_text("echo pwned\n", encoding="utf-8")
    (folder / "python3").mkdir()
    (folder / "python3" / "x").write_text("x", encoding="utf-8")
    shim.agent_env(store)
    assert sorted(path.name for path in folder.iterdir()) == wrappers
    assert set(wrappers) <= {"nod", "nod.cmd"}


def link_dir(link: Path, target: Path) -> None:
    """A junction on Windows, a symlink elsewhere, from `link` to the folder `target`; skips the test if refused."""
    try:
        if WINDOWS:
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(target, link, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"cannot create a link: {error}")


def outside_folder(tmp_path: Path) -> Path:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("the owner's file", encoding="utf-8")
    (outside / "sub").mkdir()
    (outside / "sub" / "keep2.txt").write_text("x", encoding="utf-8")
    return outside


def test_agent_env_replaces_a_linked_wrapper_folder_without_following_it(repo, tmp_path):
    """`bin` itself a link: it is removed as a link and made a real folder; the target keeps its files."""
    store = Store(repo / ".nod")
    outside = outside_folder(tmp_path)
    folder = shim.bin_dir(store)
    folder.parent.mkdir(parents=True, exist_ok=True)
    link_dir(folder, outside)
    shim.agent_env(store)
    assert (outside / "keep.txt").exists() and (outside / "sub" / "keep2.txt").exists()
    assert sorted(path.name for path in outside.iterdir()) == ["keep.txt", "sub"]
    assert folder.is_dir() and not folder.is_symlink() and not os.path.isjunction(folder)
    assert {path.name for path in folder.iterdir()} <= {"nod", "nod.cmd"} and (folder / "nod").is_file()


def test_agent_env_removes_a_linked_entry_as_a_link(repo, tmp_path):
    """A link inside `bin` goes as a link: no `rmtree` on it, nothing removed behind it, the command still starts."""
    store = Store(repo / ".nod")
    shim.agent_env(store)
    outside = outside_folder(tmp_path)
    folder = shim.bin_dir(store)
    link_dir(folder / "git", outside)
    shim.agent_env(store)
    assert (outside / "keep.txt").exists() and (outside / "sub" / "keep2.txt").exists()
    assert not (folder / "git").exists() and not (folder / "git").is_symlink()
    assert {path.name for path in folder.iterdir()} <= {"nod", "nod.cmd"}
