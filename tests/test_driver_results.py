"""Result files: the TOML the agent command writes to `{result}`."""
import os, subprocess, sys
import pytest
from the_nod.driver import results
from tests.driver_helpers import FAKE

def write(tmp_path, text):
    p = tmp_path / "r.toml"; p.write_text(text, encoding="utf-8"); return p

def test_read_brief_ok_and_missing(tmp_path):
    assert results.read_brief(write(tmp_path, 'brief = "docs/briefs/x.md"\n')) == results.BriefResult("docs/briefs/x.md")
    with pytest.raises(results.ResultError, match="no result file"):
        results.read_brief(tmp_path / "missing.toml")

def test_read_run_values(tmp_path):
    r = results.read_run(write(tmp_path, 'result = "ok"\ncontracts_total = 3\ncontracts_done = 2\n'))
    assert r == results.RunResult("ok", 3, 2, "")
    with pytest.raises(results.ResultError, match='invalid result: "maybe"'):
        results.read_run(write(tmp_path, 'result = "maybe"\n'))
    with pytest.raises(results.ResultError, match="TOML"):
        results.read_run(write(tmp_path, "result = [\n"))

def test_read_accept_frames_and_level(tmp_path):
    a = results.read_accept(write(tmp_path, 'level = 2\nresult = "solved"\nframes = [{ path = "shot.png", caption = "7 days" }]\nsteps = ["Open"]\n'))
    assert a.frames == [("shot.png", "7 days")] and a.steps == ["Open"] and a.report is None and a.blocked == ""
    with pytest.raises(results.ResultError, match='invalid level: "4"'):
        results.read_accept(write(tmp_path, 'level = 4\nresult = "solved"\n'))

def test_blocked_alone_is_enough(tmp_path):
    from the_nod.model import DECISION_KINDS
    assert "owner-action" in DECISION_KINDS
    assert results.read_brief(write(tmp_path, 'blocked = "need an API key"\n')) == results.BriefResult("", "", "need an API key")
    assert results.read_run(write(tmp_path, 'blocked = "the test environment is down"\n')).blocked == "the test environment is down"
    assert results.read_accept(write(tmp_path, 'blocked = "no test mailbox"\n')).result == "unverified"
    with pytest.raises(results.ResultError, match="no field brief"):
        results.read_brief(write(tmp_path, 'blocked = ""\n'))

def test_fake_agent_writes_result_and_prompt(tmp_path):
    result = tmp_path / "out.toml"
    env = {**os.environ, "NOD_ROOT": str(tmp_path), "NOD_CARD": "c-1aaa", "NOD_RESULT": str(result)}
    proc = subprocess.run([sys.executable, str(FAKE), "--mode", "run-ok"], input="промпт", capture_output=True, text=True, encoding="utf-8", env=env)
    assert proc.returncode == 0 and results.read_run(result).result == "ok"
    assert (tmp_path / "out.toml.prompt.txt").read_text(encoding="utf-8") == "промпт"
    assert '"type": "result"' in proc.stdout or '"type":"result"' in proc.stdout

@pytest.mark.parametrize("level", ["true", "2.0", '"2"'])
def test_level_must_be_plain_int(tmp_path, level):
    with pytest.raises(results.ResultError, match="invalid level"):
        results.read_accept(write(tmp_path, f'level = {level}\nresult = "solved"\n'))

def test_blocked_resets_other_fields(tmp_path):
    assert results.read_run(write(tmp_path, 'blocked = "x"\nresult = "maybe"\n')) == results.RunResult("stop", blocked="x")
    assert results.read_accept(write(tmp_path, 'blocked = "x"\nlevel = 9\n')) == results.AcceptResult(1, "unverified", blocked="x")
    assert results.read_brief(write(tmp_path, 'blocked = "x"\nbrief = 5\n')) == results.BriefResult("", "", "x")
    with pytest.raises(results.ResultError, match='invalid blocked: "5"'):
        results.read_run(write(tmp_path, "blocked = 5\n"))
