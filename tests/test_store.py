import pytest
from the_nod.store import Store, LoadError, slugify
from the_nod import model as m

def card(id="c-7k3q", title="Выгрузка привычек", status="backlog"):
    return m.Card(id=id, title=title, status=status, created="2026-10-20T10:00:00", source="owner")

def test_slugify():
    assert slugify('Вернуть "контраст" | #1') == "вернуть-контраст-1"
    assert len(slugify("а" * 100)) == 40

def test_save_and_load_card(tmp_path):
    s = Store(tmp_path / ".nod")
    p = s.save_card(card())
    assert p.name == "c-7k3q-выгрузка-привычек.md"
    assert s.load_card("c-7k3q").title == "Выгрузка привычек"

def test_rename_on_title_change(tmp_path):
    s = Store(tmp_path / ".nod"); s.save_card(card())
    s.save_card(card(title="Новый"))
    assert [p.name for p in (s.root / "cards").iterdir()] == ["c-7k3q-новый.md"]

def test_new_id_unique_and_short(tmp_path):
    s = Store(tmp_path / ".nod")
    ids = set()
    for _ in range(200):
        i = s.new_id("c")
        s.save_card(m.Card(id=i, title="x", status="backlog", created="x", source="owner"))
        ids.add(i)
    assert len(ids) == 200 and all(len(i) == 6 and i.startswith("c-") for i in ids)

def test_order_filters_and_appends(tmp_path):
    s = Store(tmp_path / ".nod")
    s.save_card(card("c-aaaa", "A")); s.save_card(card("c-bbbb", "B")); s.save_card(card("c-cccc", "C", "done"))
    s.set_order(["c-bbbb", "c-zzzz"])
    assert s.order() == ["c-bbbb", "c-aaaa"]
    assert "c-bbbb  B" in (s.root / "order.md").read_text(encoding="utf-8")

@pytest.mark.parametrize("lang", ["en", "ru"])
def test_order_heading_is_the_same_in_every_language(tmp_path, lang):
    """Two machines with different `lang` must not rewrite each other's heading: no diff noise in git."""
    from the_nod import i18n
    i18n.use(lang)
    s = Store(tmp_path / ".nod"); s.save_card(card("c-aaaa", "A"))
    s.set_order(["c-aaaa"])
    assert (s.root / "order.md").read_text(encoding="utf-8").splitlines() == ["# Backlog order", "", "c-aaaa  A"]

def test_order_reads_the_old_russian_heading(tmp_path):
    s = Store(tmp_path / ".nod"); s.save_card(card("c-aaaa", "A")); s.save_card(card("c-bbbb", "B"))
    (s.root / "order.md").write_text("# Порядок бэклога\n\nc-bbbb  B\nc-aaaa  A\n", encoding="utf-8")
    assert s.order() == ["c-bbbb", "c-aaaa"]

def test_load_error_names_path_and_line(tmp_path):
    s = Store(tmp_path / ".nod"); s.save_card(card())
    p = next((s.root / "cards").iterdir()); p.write_text('+++\nid = "c-7k3q\n+++\n', encoding="utf-8")
    with pytest.raises(LoadError) as e:
        s.load_card("c-7k3q")
    assert e.value.path == p and e.value.line == 2

def test_lock_and_seen(tmp_path):
    s = Store(tmp_path / ".nod")
    assert s.lock() is None
    s.write_lock("laptop", "2026-10-20T10:00:00")
    assert s.lock() == {"host": "laptop", "at": "2026-10-20T10:00:00"}
    s.mark_seen("laptop", "2026-10-20T11:00:00")
    assert s.seen() == {"laptop": "2026-10-20T11:00:00"}

def test_id_prefix_does_not_match_longer_id(tmp_path):
    s = Store(tmp_path / ".nod")
    s.save_card(card("c-7k3qz", "Длинный")); s.save_card(card("c-7k3q", "Короткий"))
    assert s.load_card("c-7k3q").title == "Короткий"
    assert [c.id for c in s.cards()] == ["c-7k3q", "c-7k3qz"]

def test_model_error_is_wrapped(tmp_path):
    s = Store(tmp_path / ".nod"); s.save_card(card())
    p = next((s.root / "cards").iterdir()); p.write_text('+++\nid = "c-7k3q"\n+++\n', encoding="utf-8")
    with pytest.raises(LoadError) as e:
        s.load_card("c-7k3q")
    assert e.value.path == p and e.value.line is None

def test_acceptance_run_decision_roundtrip_and_lock_clear(tmp_path):
    s = Store(tmp_path / ".nod")
    assert s.load_acceptance("c-7k3q") is None
    a = m.Acceptance(card="c-7k3q", level=1, result="solved", created="x")
    assert s.save_acceptance(a) == s.root / "acceptance" / "c-7k3q" / "index.md"
    assert s.load_acceptance("c-7k3q") == a
    r = m.Run(id="r-1aaa", card="c-7k3q", started="x"); s.save_run(r)
    d = m.Decision(id="d-1aaa", kind="fork", created="x", question="Q?", proposed="A", options=["A"]); s.save_decision(d)
    assert s.runs() == [r] and s.decisions() == [d]
    s.write_lock("h", "t"); s.clear_lock(); s.clear_lock()
    assert s.lock() is None

def test_rename_to_earlier_and_empty_slug_leaves_one_file(tmp_path):
    s = Store(tmp_path / ".nod"); s.save_card(card(title="Двигать срок"))
    for title in ("Арбуз", "!!!", "Яблоко"):
        s.save_card(card(title=title))
        assert len(list((s.root / "cards").iterdir())) == 1
        assert [c.id for c in s.cards()] == ["c-7k3q"]

def test_duplicate_id_raises_load_error(tmp_path):
    s = Store(tmp_path / ".nod"); p = s.save_card(card())
    twin = p.with_name("c-7k3q-копия.md"); twin.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    for call in (lambda: s.load_card("c-7k3q"), s.cards):
        with pytest.raises(LoadError, match="duplicate id c-7k3q") as e:
            call()
        assert e.value.path == twin and e.value.line is None

@pytest.mark.parametrize("bad", ["../x", "c-*", "..", "C-7k3q", "c-7k3q\n", ""])
def test_bad_id_rejected(tmp_path, bad):
    s = Store(tmp_path / ".nod")
    with pytest.raises(ValueError, match="invalid id"):
        s.load_card(bad)
    with pytest.raises(ValueError, match="invalid id"):
        s.load_acceptance(bad)
    with pytest.raises(ValueError, match="invalid id"):
        s.save_card(card(id=bad))

def test_bad_id_never_writes_outside_folder(tmp_path):
    s = Store(tmp_path / ".nod")
    with pytest.raises(ValueError, match="invalid id"):
        s.save_run(m.Run(id="../x", card="c-7k3q", started="x"))
    with pytest.raises(ValueError, match="invalid id"):
        s.save_card(card(id="../x", title="!!!"))
    assert not (s.root / "x.md").exists()

def test_add_frame_copies_small_and_skips_big(tmp_path):
    s = Store(tmp_path / ".nod")
    small = tmp_path / "A.JPG"; small.write_bytes(b"x" * 1000)
    big = tmp_path / "b.png"; big.write_bytes(b"x" * (300 * 1024 + 1))
    edge = tmp_path / "e.png"; edge.write_bytes(b"x" * (300 * 1024))
    assert s.add_frame("c-7k3q", small, 1) == "frame-1.jpg"
    assert (s.root / "acceptance" / "c-7k3q" / "frame-1.jpg").read_bytes() == b"x" * 1000
    assert s.add_frame("c-7k3q", edge, 2) == "frame-2.png"
    assert s.add_frame("c-7k3q", big, 3) is None
    assert not (s.root / "acceptance" / "c-7k3q" / "frame-3.png").exists()
    with pytest.raises(ValueError, match="invalid id"):
        s.add_frame("../x", small, 1)

def test_add_frame_rejects_unknown_extension(tmp_path):
    s = Store(tmp_path / ".nod")
    f = tmp_path / "a.txt"; f.write_bytes(b"x")
    with pytest.raises(ValueError, match="invalid extension"):
        s.add_frame("c-7k3q", f, 1)
    assert not (s.root / "acceptance" / "c-7k3q" / "frame-1.txt").exists()


BOM = b"\xef\xbb\xbf"


def test_files_with_bom_are_read(tmp_path):
    s = Store(tmp_path / ".nod")
    p = s.save_card(card())
    p.write_bytes(BOM + p.read_bytes())
    assert s.load_card("c-7k3q").title == "Выгрузка привычек"
    (s.root / "order.md").write_bytes(BOM + "c-7k3q  X\n".encode("utf-8"))
    assert s.order() == ["c-7k3q"]
    (s.root / "seen.toml").write_bytes(BOM + b'pc = "2026-10-20T10:00:00"\n')
    assert s.seen() == {"pc": "2026-10-20T10:00:00"}


def test_review_roundtrip(tmp_path):
    s = Store(tmp_path / ".nod")
    late = m.Review(week="2026-43", since="2026-10-14T00:00:00", until="2026-10-21T00:00:00",
                    generated_at="2026-10-21T00:00:00", runs=2,
                    suggestions=[m.Suggestion(1, "stuck", "period", "Текст", "applied")], body="# Обзор\n")
    early = m.Review(week="2026-42", since="a", until="b", generated_at="c")
    assert s.save_review(late) == s.root / "reviews" / "2026-43.md"
    s.save_review(early)
    assert s.load_review("2026-43") == late
    assert [r.week for r in s.reviews()] == ["2026-42", "2026-43"]
    assert s.load_review("2000-01") is None
    with pytest.raises(ValueError, match="invalid week"):
        s.load_review("../cards")
