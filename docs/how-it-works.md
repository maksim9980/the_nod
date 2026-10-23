# How Nod works

Nod is for a project where agents write the code and the owner spends their time on decisions. The owner reads what is waiting and answers it; the rest moves without them.

## Three parts

- The core, the `nod` command. It keeps the state as files in `.nod/` and is the only way to write them. Every write changes the files, rebuilds the snapshot `.nod/state.json` and commits `.nod/` with the subject `state: <what was done>`. With `[git] push = true` in the manifest it also pulls before the write and pushes after it. See [the commands](cli.md) and [the state format](state-format.md).
- The driver, `nod driver`, a process on the owner's machine. It moves cards forward whenever that needs no decision. It starts `claude -p` to write briefs, run steps and check results. It never answers a decision. See [the driver](driver.md).
- The clients: the pane in Claude Code, `nod status` in a terminal, and the [MCP server](mcp.md) for agents. The pane reads `.nod/state.json` and writes through `nod decision answer`, like a person at a terminal would.

## The life of a card

| Status | What happens | Next status |
|---|---|---|
| `backlog` | The card waits in the order of `.nod/order.md`. The driver briefs cards you or an agent added. Imported cards wait until you say yes to the next batch. | `briefing` |
| `briefing` | An agent writes the brief. | `waiting-owner` if the brief has open questions, `ready` if not |
| `waiting-owner` | Each open question is a `fork` decision. When all of them have answers, the driver applies them. | `ready` if you took every proposed answer; otherwise `briefing` again, with your answers |
| `ready` | The steps are known. The driver starts a run of the next open step. One run goes at a time, in backlog order. | `running` |
| `running` | An agent works on the step and commits code. | `ready` while steps remain or when the step waits for an owner action, `accepting` after the last step, `returned` on a stop or a hang |
| `accepting` | An agent follows the "How we check" section of the brief and records the result. | `waiting-verdict` |
| `waiting-verdict` | A `verdict` decision waits for you. | `done` or `returned` |
| `done` | The card is closed and leaves the backlog. | — |
| `returned` | The card is out of the queue until you answer the `return` or `run-stuck` decision. | `briefing`, `ready` or `backlog` |

While a card has an open decision, the driver starts no brief, run or acceptance for it. Only the check for a hung run still looks at such a card.

## Decisions

A decision is a question to the owner with a proposed answer and a list of options. The pane shows the open ones under "Waiting for you"; `nod decision list` prints them.

| Kind | Who asks | Options | What the answer does |
|---|---|---|---|
| `fork` | the driver, from section 4 of the brief | free text; the proposed answer comes first | all as proposed: the card is `ready`; otherwise the brief is written again with your answers |
| `verdict` | the driver, after an acceptance | `accept`, `return` | `accept` closes the card; `return` sends it back with your note and opens a `return` decision |
| `owner-action` | the driver or an agent, when only the owner can act | `done`, `postpone` | `done`: the work that waited goes on, the driver repeats a stopped step; `postpone`: the card goes to the bottom of the backlog |
| `return` | `nod card return`, a returned verdict, a failed brief or a stopped run | `rerun`, `backlog` | `rerun`: a new brief with your `--note`, if you give one, and the reason the card came back (for example why a run stopped): `nod decision answer <id> rerun --note "<what to change>"`; `backlog`: the bottom of the backlog |
| `run-stuck` | the driver, when a run hangs | `restart`, `backlog` | `restart`: the card is `ready` again; `backlog`: the bottom of the backlog |
| `next-batch` | the driver, when only imported cards are left | `yes`, `no` | `yes`: the first three cards go to `briefing`; `no`: asked again a day later |
| `pain` | the driver, when the backlog is empty | `wait` or a free answer | a free answer becomes a card at the top of the backlog; `wait`: asked again a day later |

`nod decision ask` also accepts the kind `brief-yes`. The driver does not ask it and does not react to it.

An `owner-action` is the one kind the pane marks "Action needed" and puts first: a login, an API key, a test card, a test environment that is down. [Owner actions for your agents](agents.md) explains how agents outside the driver ask for one.

## Who may do what

| | The owner | The driver | An agent under the driver |
|---|---|---|---|
| Answer a decision, close a card | yes | no | no |
| Return or reorder cards, record an acceptance, finish a run | yes | yes, as part of its work | no |
| Add a card, record run progress | yes | yes | yes |
| Ask a decision | yes | yes | only `owner-action` |
| Write briefs and code, run tests | — | through the agent | yes |

The driver marks every agent command with `NOD_AGENT=1`. Under it, `nod decision answer`, `nod accept`, `nod run finish`, `nod card close`, `nod card return`, `nod card move`, `nod driver`, `nod import`, `nod migrate`, `nod install`, `nod init` and `nod render --write` refuse with exit code 2, and so does `nod decision ask` with any kind other than `owner-action`. `nod render` without `--write` still prints. The MCP tools for the same commands refuse the same way. The other limits on the agent are in [SECURITY.md](../SECURITY.md).

## Where things live

- `.nod/` holds the state: cards, decisions, runs, acceptances, the backlog order, the manifest `harness.toml`, the driver lock, the weekly reviews. Everything there except a few local files is committed.
- `docs/briefs/` holds the briefs. The agent commits each one as `docs(brief): <slug>`.
- The code the agents write is committed to the current branch.

The state is plain text, so a merge conflict in `.nod/` is solved like any other: by editing files. Nod reads the files again on every command.
