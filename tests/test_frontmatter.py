from the_nod import frontmatter as fm
import pytest


def test_roundtrip_all_types():
    meta = {"id": "c-7k3q", "title": 'Вернуть "контраст" | #1 \\ путь', "n": 3,
            "ratio": 0.5, "done": False, "brief": None, "tags": ["а", "b"],
            "steps": [{"n": 1, "title": "Шаг «один»", "done": True}]}
    body = "Тело\n\nс пустой строкой и +++ внутри\n"
    text = fm.dump(meta, body)
    meta2, body2 = fm.parse(text)
    assert meta2 == {k: v for k, v in meta.items() if v is not None}
    assert body2 == body


def test_dump_starts_and_ends_with_fences():
    text = fm.dump({"id": "x"}, "b")
    assert text.startswith("+++\n") and "\n+++\n" in text


def test_parse_without_frontmatter_returns_empty_meta():
    assert fm.parse("просто текст") == ({}, "просто текст")


def test_parse_error_names_line():
    with pytest.raises(fm.FrontmatterError) as e:
        fm.parse('+++\nid = "x\n+++\n')
    assert e.value.line == 2


def test_roundtrip_empty_body_and_no_trailing_newline():
    assert fm.parse(fm.dump({"id": "x"}, "")) == ({"id": "x"}, "")
    assert fm.parse(fm.dump({"id": "x"}, "без перевода строки")) == (
        {"id": "x"}, "без перевода строки")


def test_body_line_with_fence_stays_in_body():
    body = "+++\nещё одна рамка\n+++\n"
    assert fm.parse(fm.dump({"id": "x"}, body)) == ({"id": "x"}, body)


def test_parse_crlf():
    meta, body = fm.parse('+++\r\nid = "x"\r\n+++\r\nтело\r\n')
    assert meta == {"id": "x"} and body == "тело\r\n"


def test_parse_unclosed_frontmatter_raises():
    with pytest.raises(fm.FrontmatterError):
        fm.parse('+++\nid = "x"\n')


def test_control_chars_and_key_order_roundtrip():
    meta = {"z": "a\nb\tc\x01\r", "a": [], "m-k": 1.5}
    meta2, _ = fm.parse(fm.dump(meta, ""))
    assert meta2 == meta and list(meta2) == ["z", "a", "m-k"]


def test_dump_rejects_unsupported_type():
    with pytest.raises(fm.FrontmatterError):
        fm.dump({"x": {"nested": 1}}, "")
