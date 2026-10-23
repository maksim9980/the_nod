import json, os, subprocess, sys, tomllib
from pathlib import Path

from the_nod import __version__
from the_nod.cli import main
from the_nod.mcp import server

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
SKIP_PARTS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".nod", ".superpowers", ".claude", ".claude-plugin", "the_nod.egg-info", "types"}


def test_manifest_names_and_versions_agree():
    plugin = json.loads(MANIFEST.read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert plugin["name"] == "nod" == market["plugins"][0]["name"] and market["plugins"][0]["source"] == "./"
    assert plugin["version"] == server.SERVER_INFO["version"] == __version__
    assert plugin["userConfig"]["diag"]["default"] is False  # the pane stays quiet in the chat unless turned on
    assert pyproject["project"]["dynamic"] == ["version"]
    assert pyproject["tool"]["setuptools"]["dynamic"]["version"] == {"attr": "the_nod.__version__"}
    assert "version" not in market["plugins"][0]


def test_manifest_paths_exist():
    plugin = json.loads(MANIFEST.read_text(encoding="utf-8"))
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert (ROOT / plugin["types"]).is_file() and (ROOT / "hooks" / hooks["modules"][0]).resolve().is_file()
    assert not (ROOT / "mod" / "nod-pane" / ".claude-plugin" / "plugin.json").exists()
    assert plugin["mcpServers"]["nod"]["args"] == ["-P", "${CLAUDE_PLUGIN_ROOT}/the_nod/__main__.py", "mcp"]


def test_mcp_entry_runs_with_mixed_separators(tmp_path):
    plugin = json.loads(MANIFEST.read_text(encoding="utf-8"))
    arg = plugin["mcpServers"]["nod"]["args"][1].replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT))  # `D:\…\Nod/the_nod/__main__.py`
    done = subprocess.run([sys.executable, "-I", "-P", arg, "--help"], capture_output=True, text=True, encoding="utf-8", cwd=tmp_path, timeout=60)
    assert done.returncode == 0 and "usage: nod" in done.stdout


def test_core_writes_nothing_under_root(repo, capsys):
    """The state of a project lives in its own `.nod`; the plugin root is unchanged after init and card add."""
    def snapshot():
        files = {}
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in SKIP_PARTS]
            for name in filenames:
                path = Path(dirpath) / name
                files[path] = path.stat().st_mtime_ns
        return files
    before = snapshot()
    assert before, "the snapshot of the root is empty: the check checks nothing"
    main(["--root", str(repo), "init"]); main(["--root", str(repo), "card", "add", "Check"]); capsys.readouterr()
    assert snapshot() == before
