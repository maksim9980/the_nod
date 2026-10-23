# The MCP server

`nod mcp` is an MCP server over stdio. It gives agents the `nod` commands as tools, so an agent can add a card or ask the owner a question without a shell.

## In Claude Code

The plugin declares the server itself: `claude mcp list` shows it as `plugin:nod:nod`. Claude Code starts it as `python -P <plugin folder>/the_nod/__main__.py mcp`, with the session folder as the current folder. A `.mcp.json` is needed only where the plugin is not installed.

The server runs `python` by that exact name. If `python` on PATH is missing or is the Microsoft Store stub, the server does not start. Put a real `python` on PATH, or turn off the App Execution Alias for `python.exe` in Windows settings. `nod doctor` shows the problem in its `python` row.

On macOS and Linux the same rule bites harder, because stock Ubuntu and macOS have `python3` only. The plugin manifest has no per-system command, so the server does not start until a command `python` exists:

- Debian and Ubuntu: `sudo apt install python-is-python3`.
- macOS: make `python` a link to `python3` in a folder that is on the PATH of Claude Code, for example `ln -s "$(command -v python3)" <folder in PATH>/python`.

`nod doctor` shows this in its `MCP server` row, and the `python` row then reports the command it found, for example `3.13 (python3)`. The pane and the driver do not need a `python` command: the pane also tries `python3`, and the driver and its login job use the interpreter that started them. The default commands let the driver's agents run `python3 -m pytest` and `python3 -m the_nod` as well as the `python` forms. Two things ran live on Linux, under WSL with Ubuntu 24.04: the core test suite, on Python 3.12, below the 3.13 that Nod requires, and installing and removing the autostart. Starting at login or after a reboot was not tested. The pane's `python3` fallback, the MCP server started as `python` and the doctor rows above have not run on a real macOS or Linux machine; tests cover them.

## Codex

Not verified: no Codex setup has been tested. This entry in `~/.codex/config.toml` follows the Codex documentation:

```toml
[mcp_servers.nod]
command = "python"
args = ["-P", "<plugin folder>/the_nod/__main__.py", "--root", "<project folder>", "mcp"]
```

With the package installed, `command = "nod"` and `args = ["--root", "<project folder>", "mcp"]` do the same. Where only `python3` exists, use `command = "python3"`.

## Protocol

JSON-RPC 2.0, one message per line. Protocol versions: `2025-06-18`, `2025-03-26`, `2024-11-05`. The server calls itself `nod`, version `0.1.0`, and answers `initialize`, `ping`, `tools/list` and `tools/call`. Notifications get no answer.

The state root is `--root`, or the repository of the current folder. If the server finds the state at start, it keeps that root. If not, it still starts and answers `tools/list`, and a tool call returns `isError` with `no state: run nod init`; the core then looks for the state again on every call. An explicit `--root` that leads to no state is refused with exit code 2.

Each tool call runs the matching `nod` command with `--json` and returns its output as text in `content`. A non-zero exit code gives `isError: true`. Wrong tool arguments (a missing required one, a wrong type, an extra key) also come back as a normal result with `isError: true`. Protocol errors:

| Code | When |
|---|---|
| `-32700` | the line is not JSON |
| `-32600` | a batch of requests, a message that is not an object, or no `"jsonrpc": "2.0"` |
| `-32601` | an unknown method |
| `-32602` | an unknown tool, or `params` that is not an object |

The tool descriptions use the language the server started in: `NOD_LANG`, then `lang` of the manifest found at start, then English. The output of each call follows the language of its state.

An agent started by the driver has `NOD_AGENT=1`, and so does the server it starts. Then the tools that answer for the owner (`card_move`, `card_close`, `card_return`, `decision_answer`, `accept`, `run_finish`) return `isError` with `this command is not available to the driver's agent`. `decision_ask` with any `kind` other than `owner-action` returns `isError` too.

## Tools

| Tool | Command | What it does |
|---|---|---|
| `status` | `nod status --peek` | the snapshot, without marking a visit |
| `card_add` | `nod card add` | adds a card; returns its id |
| `card_move` | `nod card move` | moves a card: exactly one of `top`, `bottom`, `before`, `after` |
| `card_close` | `nod card close` | closes a card |
| `card_return` | `nod card return` | returns a card with a note |
| `card_show` | `nod card show` | prints a whole card |
| `decision_list` | `nod decision list` | the open decisions, or all with `all` |
| `decision_ask` | `nod decision ask` | asks the owner; returns the decision id |
| `decision_answer` | `nod decision answer` | answers a decision |
| `run_start` | `nod run start` | starts a run; returns its id |
| `run_progress` | `nod run progress` | records the finished pieces of a run |
| `run_finish` | `nod run finish` | finishes a run with its result and spend |
| `accept` | `nod accept` | records an acceptance; `frames` is a list of `{path, caption}` |
| `review_week` | `nod review week` | writes the weekly review |
| `review_mark` | `nod review mark` | sets a suggestion to `applied` or `proposed` |
| `doctor` | `nod doctor` | checks the machine; writes nothing |

`init`, `install`, `migrate`, `import`, `render` and `driver` are not tools. `init`, `install` and `migrate` change the machine or the repository, which is the owner's call. `import` is a one-off, `render` prints Markdown for people, and `driver` keeps running until it is stopped.
