"""A fake agent: plays the brief/run/accept command for the driver tests. No model.

The brief it writes is English; `--lang ru` writes the same brief in Russian.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "claude" / "result.json"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 1016  # 1 KB

# The pieces of the brief in each language: the labels follow decision R5.
BRIEF = {
    "en": {
        "title": "# Export habits to CSV",
        "status": "Date: 2026-10-21. Status: draft.",
        "fork": "2. Question: Keep history? Proposed: yes, 30 days. Why: enough to debug. "
                "Options: yes, 30 days | no | forever.",
        "no_fork": "1. No forks. Why: all clear.",
        "steps": "1. CSV writer\n2. Export button\n",
        "garbage": "text\n3. \n- marker\n",
        "section": "Section {n}",
        "ten": "Steps",
        "body": "Text.",
    },
    "ru": {
        "title": "# Экспорт привычек в CSV",
        "status": "Дата: 2026-10-21. Статус: черновик.",
        "fork": "2. Вопрос: Хранить ли историю? Предлагаю: да, 30 дней. Почему: хватит для разбора. "
                "Варианты: да, 30 дней | нет | навсегда.",
        "no_fork": "1. Развилок нет. Почему: всё ясно.",
        "steps": "1. Запись CSV\n2. Кнопка экспорта\n",
        "garbage": "текст\n3. \n- маркер\n",
        "section": "Раздел {n}",
        "ten": "Карточки",
        "body": "Текст.",
    },
}
FORK = BRIEF["en"]["fork"]
TITLE = BRIEF["en"]["title"][2:]
STEPS = ["CSV writer", "Export button"]
LANG = "en"  # the brief language, set from --lang by main()


def env(name: str) -> str:
    return os.environ.get(name, "")


def root() -> Path:
    return Path(env("NOD_ROOT") or ".")


def write_result(text: str) -> None:
    path = Path(env("NOD_RESULT"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def claude_json(**changes) -> str:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data.update(changes)
    return json.dumps(data, ensure_ascii=False)


def brief_text(forks: bool, garbage: bool, lang: str = "en") -> str:
    words = BRIEF[lang]
    four = words["fork"] if forks else words["no_fork"]
    ten = words["garbage"] if garbage else words["steps"]
    parts = [words["title"], "", words["status"], ""]
    for n in range(1, 11):
        title = words["ten"] if n == 10 else words["section"].format(n=n)
        body = four if n == 4 else ten if n == 10 else words["body"]
        parts += [f"## {n}. {title}", body, ""]
    return "\n".join(parts)


def commit_brief(card: str, rel: str) -> None:
    for args in (["add", rel], ["commit", "-m", f"docs(brief): {card}"]):
        subprocess.run(["git", *args], cwd=root(), check=False, capture_output=True)


def write_brief(forks: bool = False, garbage: bool = False, *, finish: bool = True,
                result: bool = False) -> None:
    """The brief file; `finish` also commits it and writes the result file, as the prompt asks; `result` writes only the result."""
    card = env("NOD_CARD")
    rel = f"docs/briefs/{card}.md"
    target = root() / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(brief_text(forks, garbage, LANG), encoding="utf-8")
    if finish:
        commit_brief(card, rel)
    if finish or result:
        write_result(f'brief = "{rel}"\n')


def brief_forks_then_ok() -> None:
    counter = root() / ".nod" / "driver" / "fake-count"
    counter.parent.mkdir(parents=True, exist_ok=True)
    count = int(counter.read_text(encoding="utf-8")) if counter.exists() else 0
    counter.write_text(str(count + 1), encoding="utf-8")
    write_brief(forks=count == 0)


def brief_auth() -> int:
    print(claude_json(is_error=True, result="Failed to authenticate: OAuth session expired"))
    return 1


def run_ok() -> None:
    write_result('result = "ok"\ncontracts_total = 3\ncontracts_done = 3\n')
    print(claude_json())


def run_progress() -> None:
    subprocess.run([sys.executable, "-m", "the_nod", "--root", env("NOD_ROOT"),
                    "run", "progress", env("NOD_RUN"), "--contracts-done", "1"],
                   check=False, capture_output=True)
    run_ok()


def run_stop() -> None:
    write_result('result = "stop"\nnote = "stop: test"\n')


def run_slow() -> None:
    time.sleep(2)
    run_ok()


def run_delete_card() -> None:
    for card in (root() / ".nod" / "cards").glob(f"{env('NOD_CARD')}*.md"):
        card.unlink()
    run_ok()


def accept_ok() -> None:
    (root() / "shot.png").write_bytes(PNG)
    write_result('level = 2\nresult = "solved"\nevidence = "14 of 14"\n'
                 'frames = [{ path = "shot.png", caption = "7 days" }]\n'
                 'steps = ["Open the site"]\n')


def print_path() -> None:
    print(env("PATH"))


def call_nod() -> None:
    """Runs `nod --help` through the shell, as an agent does, and prints what it printed."""
    done = subprocess.run("nod --help", shell=True, capture_output=True, text=True, encoding="utf-8")
    sys.stdout.write(done.stdout)
    sys.stderr.write(done.stderr)


def touch() -> None:
    activity = Path(env("NOD_RESULT") + ".activity")
    for _ in range(10):
        activity.write_text(str(time.time()), encoding="utf-8")
        time.sleep(0.2)


def spawn_hang() -> None:
    """A grandchild that outlives a killed agent unless the agent's whole group dies; its pid goes to FAKE_GRANDCHILD_PID."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    Path(env("FAKE_GRANDCHILD_PID")).write_text(str(child.pid), encoding="utf-8")
    time.sleep(60)


def exit_code(code: int):
    return lambda: code


MODES = {
    "brief-ok": write_brief,
    "brief-forks": lambda: write_brief(forks=True),
    "brief-forks-then-ok": brief_forks_then_ok,
    "brief-garbage": lambda: write_brief(garbage=True),
    "brief-file-only": lambda: write_brief(finish=False),
    "brief-nocommit": lambda: write_brief(finish=False, result=True),
    "brief-file-fail": lambda: write_brief(finish=False) or 1,
    "brief-fail": exit_code(1),
    "brief-noresult": exit_code(0),
    "brief-blocked": lambda: write_result('blocked = "need an API key: put it into .env"\n'),
    "brief-auth": brief_auth,
    "run-ok": run_ok,
    "run-blocked": lambda: write_result('blocked = "the test environment on :8001 is down"\n'),
    "run-progress": run_progress,
    "run-stop": run_stop,
    "run-hang": lambda: time.sleep(60),
    "hang": lambda: time.sleep(60),
    "spawn-hang": spawn_hang,
    "run-slow": run_slow,
    "run-delete-card": run_delete_card,
    "accept-ok": accept_ok,
    "accept-fail": exit_code(1),
    "fail": exit_code(1),
    "touch": touch,
    "path": print_path,
    "nod": call_nod,
}


def main() -> int:
    global LANG
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--lang", choices=tuple(BRIEF), default="en")
    args = parser.parse_args()
    LANG = args.lang
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    prompt = sys.stdin.buffer.read().decode("utf-8")
    if env("NOD_RESULT"):
        saved = Path(env("NOD_RESULT") + ".prompt.txt")
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_text(prompt, encoding="utf-8")
    if args.mode == "echo":
        sys.stdout.write(prompt)
        return 0
    if args.mode not in MODES:
        print("unknown mode", file=sys.stderr)
        return 2
    code = MODES[args.mode]()
    return code if isinstance(code, int) else 0


if __name__ == "__main__":
    sys.exit(main())
