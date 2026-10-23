from the_nod import i18n, model as m, render
from the_nod.cli import main
from the_nod.store import Store
from tests.conftest import git


def _seed(root):
    s = Store(root / ".nod")
    s.save_card(m.Card(id="c-aaaa", title="A", status="ready", created="x", source="owner", brief="docs/briefs/a.md",
                       steps=[m.Step(1, "Один", True), m.Step(2, "Два")], body="Тело A\n\n"))
    s.save_card(m.Card(id="c-bbbb", title="B", status="backlog", created="x", source="owner"))
    s.save_card(m.Card(id="c-cccc", title="C", status="done", created="x", source="owner",
                       closed_at="2026-10-19T00:00:00", body="Тело C"))
    s.save_card(m.Card(id="c-dddd", title="D", status="done", created="x", source="owner", closed_at="2026-10-20T01:00:00"))
    s.save_card(m.Card(id="c-eeee", title="E", status="done", created="x", source="owner"))
    s.set_order(["c-bbbb", "c-aaaa"])
    return s


def test_backlog_render_order_and_steps(tmp_path):
    s = _seed(tmp_path)
    text = render.backlog(s)
    assert text.index("\n## B\n") < text.index("\n## A\n") and "## C" not in text
    assert "Brief: docs/briefs/a.md" in text and "1. ~~Один~~" in text and "2. Два" in text
    assert "## ~~C~~ — DONE (2026-10-19)" in render.archive(s)


def test_backlog_exact_text(tmp_path):
    s = _seed(tmp_path)
    assert render.backlog(s) == (
        "# BACKLOG — printed from .nod\n\n"
        "> The source of truth is .nod/. nod render backlog prints this file; edits by hand are lost.\n\n"
        "## Active tasks (by priority)\n"
        "\n## B\n\n\n---\n"
        "\n## A\n\nBrief: docs/briefs/a.md\n\nТело A\n1. ~~Один~~\n2. Два\n\n---\n"
    )


def test_backlog_exact_text_in_russian(tmp_path):
    s = _seed(tmp_path)
    i18n.use("ru")
    assert render.backlog(s) == (
        "# BACKLOG — печатается из .nod\n\n"
        "> Источник правды — .nod/. Этот файл печатает nod render backlog; правки руками теряются.\n\n"
        "## Активные задачи (по приоритету)\n"
        "\n## B\n\n\n---\n"
        "\n## A\n\nБриф: docs/briefs/a.md\n\nТело A\n1. ~~Один~~\n2. Два\n\n---\n"
    )


def test_archive_exact_text(tmp_path):
    s = _seed(tmp_path)
    assert render.archive(s) == (
        "# BACKLOG-ARCHIVE — printed from .nod\n\n"
        "> The source of truth is .nod/. nod render archive prints this file; edits by hand are lost.\n"
        "\n## ~~D~~ — DONE (2026-10-20)\n\n\n---\n"
        "\n## ~~C~~ — DONE (2026-10-19)\n\nТело C\n\n---\n"
        "\n## ~~E~~ — DONE (?)\n\n\n---\n"
    )


def test_archive_exact_text_in_russian(tmp_path):
    s = _seed(tmp_path)
    i18n.use("ru")
    assert render.archive(s) == (
        "# BACKLOG-ARCHIVE — печатается из .nod\n\n"
        "> Источник правды — .nod/. Этот файл печатает nod render archive; правки руками теряются.\n"
        "\n## ~~D~~ — СДЕЛАНО (2026-10-20)\n\n\n---\n"
        "\n## ~~C~~ — СДЕЛАНО (2026-10-19)\n\nТело C\n\n---\n"
        "\n## ~~E~~ — СДЕЛАНО (?)\n\n\n---\n"
    )


def test_render_command_write(repo, capsys):
    s = _seed(repo)
    git(repo, "add", "-A"); git(repo, "commit", "-m", "seed")
    before = git(repo, "status", "--porcelain")
    target = repo / "BACKLOG.md"
    assert main(["--root", str(s.root), "render", "backlog", "--write", str(target)]) == 0
    assert capsys.readouterr().out == f"wrote {target}\n"
    assert target.read_text(encoding="utf-8") == render.backlog(s)
    assert git(repo, "status", "--porcelain").replace("?? BACKLOG.md\n", "") == before
    assert main(["--root", str(s.root), "render", "archive"]) == 0
    assert capsys.readouterr().out == render.archive(s)


def test_render_write_to_folder_is_clean_error(tmp_path, capsys):
    s = _seed(tmp_path)
    folder = tmp_path / "out"
    folder.mkdir()
    assert main(["--root", str(s.root), "render", "backlog", "--write", str(folder)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "Traceback" not in err and str(folder) in err
