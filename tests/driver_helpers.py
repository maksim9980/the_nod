"""Shared helpers of the driver tests: the fake agent, the manifest, the environment."""
import sys
from pathlib import Path

from the_nod.cli import main
from the_nod.store import Store
from tests.conftest import git

FAKE = Path(__file__).with_name("fake_agent.py")
REPO_ROOT = Path(__file__).resolve().parent.parent


def fake(mode: str, lang: str = "en") -> str:
    """The fake agent command; `lang` is the language of the brief it writes."""
    tail = f" --lang {lang}" if lang != "en" else ""
    return f'"{sys.executable}" "{FAKE}" --mode {mode}{tail}'


def setup(repo, capsys, *, brief="brief-ok", run="run-ok", accept="accept-ok", lang: str | None = None,
          push: bool = True) -> Store:
    """`nod init`, a manifest with three fake agent commands, a commit of the state.

    `lang` also goes into the manifest, and the fake agent writes its brief in it.
    `push` is `[git] push`: on by default, the driver tests are about the driver that syncs with origin.
    """
    main(["--root", str(repo), "init"])
    commands = "\n".join(f"{kind} = '{fake(mode, lang or 'en')}'" for kind, mode in
                         (("brief", brief), ("run", run), ("accept", accept)))
    head = f'lang = "{lang}"\n' if lang else ""
    git_table = f"[git]\npush = {'true' if push else 'false'}\n"
    (repo / ".nod" / "harness.toml").write_text(
        f'{head}adapter = "default"\ndriver_host = ""\n[commands]\n{commands}\n{git_table}', encoding="utf-8")
    git(repo, "add", ".nod/harness.toml")
    git(repo, "commit", "-m", "state: harness")
    capsys.readouterr()
    return Store(repo / ".nod")


def env_for_tests(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))


def driver_run(repo, *args, capsys):
    code = main(["--root", str(repo), "driver", *args])
    out = capsys.readouterr()
    return code, out.out, out.err


def add_card(repo, capsys, title: str = "Export habits to CSV") -> str:
    """`nod card add` and the new card id."""
    main(["--root", str(repo), "card", "add", title])
    return capsys.readouterr().out.strip()
