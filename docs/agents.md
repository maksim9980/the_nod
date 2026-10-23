# Owner actions for your agents

Some work needs the owner's hands: a login to claude, an API key, a test card, a test environment that is down. Nod has a decision kind for that, `owner-action`. The pane puts it first under "Waiting for you", marked "Action needed", with two answers: `done` and `postpone`.

The agents the driver starts already know the rule: it is in the driver prompts. Agents that work outside the driver do not, such as your own Claude Code session in the project. Put the rule into the instructions of the project, the `CLAUDE.md` or `AGENTS.md` at the repository root, so those agents open a decision instead of asking in the chat, where the question gets lost.

How the driver treats the decision:

- With `--card <id>`, the card waits: the driver starts no brief, run or acceptance for a card with an open decision. `done` lets the work go on. `postpone` moves the card to the bottom of the backlog.
- Without `--card`, the driver ignores the decision. Only the agent that asked reads the answer.

The pane writes the answer into the state and sends nothing to the chat, so the agent has to read the answer itself.

The answers are the identifiers `done` and `postpone` in both languages. A Russian pane labels them in Russian, but the agent reads `done` or `postpone` from `nod decision list --json`.

## Commit attribution

The driver prompts do not tell the agents how to sign their commits. Whether an agent commit gets a `Co-Authored-By` line follows your Claude Code attribution settings, as it does in your own sessions. The agents also load the rest of your Claude Code setup, such as your global `CLAUDE.md`, so a rule you keep there reaches them too.

`--setting-sources project` in your own manifest commands skips your user settings, and your attribution setting with them: the agents then follow Claude Code's default, unless the project's own `.claude/settings.json` sets it.

## The rule in English

~~~markdown
## Owner actions

When the work needs something only the owner can do, do not ask in the chat. Examples: a login to claude, an API key, a test card, a test environment that is down. Open a decision instead. The owner sees it on the Nod pane under "Waiting for you", marked "Action needed".

A driver agent (`NOD_AGENT=1`) tells two cases apart. A line `blocked = "<what to do>"` in the result file stops the step, and the driver opens the decision itself. Then do not run `nod decision ask`, or there will be two decisions.

Other agents, and driver steps that can go on without the owner, open the decision themselves:

```
nod decision ask --kind owner-action --question "<what to do>" --proposed done --option done --option postpone
```

Add `--card <id>` when the blocker belongs to a card. The command prints the decision id; remember it.
Before you go on with the blocked work, read `nod decision list --all --json` and find the decision by its id.
The answer `done`: the owner did it, go on. The answer `postpone`: the driver moves the card back to the backlog. Do not return to this work, and end the step with "postponed by the owner".
The pane sends nothing to the chat: read the answer yourself.
If `nod` is not on PATH, use the MCP tool `decision_ask` of the `nod` server, or the command from the second line of the `/nod` answer.
~~~

## The rule in Russian

~~~markdown
## Действия владельца

Если работе нужно то, что может сделать только владелец, не спрашивай в чате. Например: вход в claude, ключ API, тестовая карта, упавший тестовый стенд. Заведи решение: владелец увидит его на панели Nod в зоне «Ждёт тебя» с меткой «Нужно действие».

Агент драйвера (`NOD_AGENT=1`) различает два случая. Строка `blocked = "<что сделать>"` в файле результата останавливает шаг, и решение драйвер заводит сам. Тогда не запускай `nod decision ask`: решений станет два.

Остальные агенты и шаги драйвера, которые могут идти дальше без владельца, заводят решение сами:

```
nod decision ask --kind owner-action --question "<что сделать>" --proposed done --option done --option postpone
```

Если блокер относится к карточке, добавь `--card <id>`. Команда печатает id решения. Запомни его.
Прежде чем вернуться к заблокированной работе, прочитай `nod decision list --all --json` и найди решение по id.
Ответ `done` — владелец всё сделал, продолжай. Ответ `postpone` — драйвер вернёт карточку в бэклог. К этой работе не возвращайся и закончи шаг ответом «отложено владельцем».
Панель ничего не пишет в чат: ответ читай сам.
Если `nod` нет в PATH, используй MCP-инструмент `decision_ask` сервера `nod` или команду из второй строки ответа `/nod`.
~~~
