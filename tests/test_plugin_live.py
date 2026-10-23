"""Live install of the plugin from a folder marketplace into a clean CLAUDE_CONFIG_DIR.

Runs only with NOD_CLAUDE=<path to the claude executable>. The real ~/.claude of the person is not touched.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from the_nod.paths import NO_WINDOW

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    not os.environ.get("NOD_CLAUDE"), reason="needs NOD_CLAUDE=<path to the claude executable>"
)

_DROP = ("CLAUDE_CODE_PLUGIN_DIRS", "CLAUDE_CODE_PLUGIN_DIR_WATCH")


def clean_env(tmp_path: Path) -> dict[str, str]:
    """An environment with HOME and the Claude config inside tmp_path, and no inline plugins."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in _DROP}
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CLAUDE_CONFIG_DIR"] = str(home / ".claude")
    return env


def show(text: str) -> None:
    """Prints the engine output; characters outside the console encoding are replaced."""
    enc = sys.stdout.encoding or "utf-8"
    print(text.encode(enc, errors="replace").decode(enc))


def run(argv, env, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        creationflags=NO_WINDOW,
    )


def test_install_from_folder_marketplace(tmp_path):
    claude = os.environ["NOD_CLAUDE"]
    env = clean_env(tmp_path)
    done = run([claude, "plugin", "install", "nod", "--marketplace", str(ROOT), "--json"], env)
    show(done.stdout + done.stderr)
    assert done.returncode == 0 and json.loads(done.stdout.strip().splitlines()[-1])["outcome"] == "ok"
    registry = json.loads(
        (tmp_path / "home" / ".claude" / "plugins" / "installed_plugins.json").read_text(encoding="utf-8")
    )
    assert registry["plugins"]["nod@nod"][0]["version"] == "0.1.0"
    listing = run([claude, "plugin", "list"], env).stdout
    show(listing)
    assert "nod@nod" in listing and f"Read from: {ROOT}" in listing
    mcp = run([claude, "mcp", "list"], env, cwd=tmp_path).stdout
    show(mcp)
    assert "plugin:nod:nod" in mcp and "Connected" in mcp
