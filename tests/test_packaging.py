import os
import subprocess
import sys
import tomllib
from pathlib import Path

from tests.driver_helpers import REPO_ROOT


def test_pyproject_declares_nod_script():
    data = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["build-system"]["build-backend"] == "setuptools.build_meta"
    assert data["project"]["scripts"]["nod"] == "the_nod.cli:main"


def _package_dir() -> Path:
    return Path(__file__).parent.parent / "the_nod"


def test_every_python_folder_is_a_package():
    """`packages.find` skips a folder without `__init__.py`: its modules would be missing from the wheel."""
    missing = sorted(
        folder.relative_to(_package_dir()).as_posix()
        for folder in [_package_dir(), *(p for p in _package_dir().rglob("*") if p.is_dir())]
        if "__pycache__" not in folder.parts and any(folder.glob("*.py")) and not (folder / "__init__.py").exists()
    )
    assert missing == []


def test_package_data_covers_every_data_file():
    """The prompts are the only non-Python files of the package; the globs of `package-data` must reach all of them."""
    data = tomllib.loads((_package_dir().parent / "pyproject.toml").read_text(encoding="utf-8"))
    globs = data["tool"]["setuptools"]["package-data"]["the_nod"]
    shipped = {p for pattern in globs for p in _package_dir().glob(pattern)}
    on_disk = {p for p in _package_dir().rglob("*") if p.is_file() and p.suffix not in {".py", ".pyc"}}
    assert on_disk and on_disk <= shipped, sorted(str(p.relative_to(_package_dir())) for p in on_disk - shipped)
    languages = {p.parent.name for p in shipped}
    assert {"en", "ru"} <= languages


def test_main_runs_as_script_without_pythonpath(tmp_path):
    main_py = REPO_ROOT / "the_nod" / "__main__.py"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    done = subprocess.run([sys.executable, "-I", "-P", str(main_py).replace("\\", "/"), "--help"],
                          capture_output=True, text=True, encoding="utf-8", cwd=tmp_path, env=env, timeout=60)
    assert done.returncode == 0 and done.stdout.startswith("usage: nod")
