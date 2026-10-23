"""The spend of a command: the `claude -p` JSON and the transcripts."""
import json
from pathlib import Path
from the_nod.driver import usage

FIXTURE = Path(__file__).parent / "fixtures" / "claude" / "result.json"

def test_from_claude_json_picks_last_result_line():
    raw = FIXTURE.read_text(encoding="utf-8").strip()
    data = json.loads(raw)
    expected = sum(int(m[k]) for m in data["modelUsage"].values() for k in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens"))
    u = usage.from_claude_json("noise\n" + raw + "\n")
    assert u.tokens == expected and u.session == data["session_id"] and u.minutes == round(data["duration_ms"] / 60000)

def test_no_json_gives_none_and_measure_zeros(tmp_path):
    assert usage.from_claude_json("just text") is None
    assert usage.measure("just text", tmp_path) == usage.Usage()

def test_auth_failure_detected_only_on_is_error():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bad = json.dumps({**data, "is_error": True, "result": "Failed to authenticate: OAuth session expired"})
    assert usage.auth_failure(bad) == "Failed to authenticate: OAuth session expired"
    assert usage.auth_failure(json.dumps({**data, "is_error": False, "result": "OAuth upgrade done"})) is None
    assert usage.auth_failure("text") is None

def test_project_slug():
    assert usage.project_slug(Path("C:/work/tidepool")) == "C--work-tidepool"
    assert usage.project_slug(Path("C:/Users/Хозяин/x y")) == "C--Users--------x-y"

def test_counts_from_transcripts(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = tmp_path / "proj"; sid = "abc"
    d = tmp_path / ".claude" / "projects" / usage.project_slug(root)
    (d / sid / "subagents").mkdir(parents=True)
    for n in (1, 2): (d / sid / "subagents" / f"agent-{n}.jsonl").write_text("{}\n", encoding="utf-8")
    (d / f"{sid}.jsonl").write_text('{"a":1}\n{"tool_use_result":{"is_error":true}}\n{"x":{"is_error": true}}\n', encoding="utf-8")
    assert usage.count_agents(root, sid) == 2 and usage.count_tool_errors(root, sid) == 2
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    measured = usage.measure(json.dumps({**data, "session_id": sid}), root)
    assert measured.agents == 2 and measured.tool_errors == 2 and measured.tokens > 0

def test_measure_survives_non_numeric_fields(tmp_path):
    bad = json.dumps({"type": "result", "duration_ms": "long", "total_cost_usd": {}})
    assert usage.measure(bad, tmp_path) == usage.Usage()
