# tests/test_spend.py
import pytest

from the_nod.model import ModelError, Spend
from the_nod.store import Store


def test_spend_roundtrip_and_order(tmp_path):
    s = Store(tmp_path / ".nod")
    p = s.save_spend(Spend(kind="brief", card="c-aaaa", at="2026-10-21T10:00:00", tokens=5, cost_usd=0.5))
    assert p.name == "2026-10-21T10-00-00-brief-c-aaaa.md" and p.parent.name == "usage"
    s.save_spend(Spend(kind="accept", card="c-aaaa", at="2026-10-20T09:00:00"))
    got = s.spends()
    assert [x.at for x in got] == ["2026-10-20T09:00:00", "2026-10-21T10:00:00"] and got[1].cost_usd == 0.5


def test_spends_without_folder_is_empty(tmp_path):
    s = Store(tmp_path / ".nod")
    assert s.spends() == []
    assert not (s.root / "usage").exists()


def test_spend_rejects_unknown_kind():
    with pytest.raises(ModelError, match="kind"):
        Spend.from_meta({"kind": "run", "card": "c-aaaa", "at": "x"})
