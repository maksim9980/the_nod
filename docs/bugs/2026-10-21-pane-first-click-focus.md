# Claude Code bug report: the first click on a mod pane only takes the focus

How to send it: run `claude` in a terminal, type `/bug` and paste the text below, or open an issue
in the Claude Code repository on GitHub. A screenshot of the pane is optional.

---

## Desktop pane (plugin `Pane`): the first click only focuses the pane, the Button under the cursor is not pressed

**Environment**
- Claude Desktop (Code tab), Windows 11 Pro 10.0.26100
- Claude Code engine 2.1.299 (`claude.exe --version` → `2.1.299 (Claude Code)`)
- Surface: `desktop` (same pane drawn through `ui.render` with `component: 'Pane'`)
- Plugin loaded via `CLAUDE_CODE_PLUGIN_DIRS` (also reproduced with the session's hot-reload dev-mods folder)

**What happens**
A plugin opens a pane with `$.ui.open({ id, title })` (no `focus`) and draws `Button` elements in it. While the composer (prompt field) holds the keyboard, the first mouse click on a Button in the pane does not raise `ui.press`: it only moves the keyboard focus to the pane. The second click on the same Button raises `ui.press`. Every time the keyboard returns to the composer (the person types a message), the next click on the pane is swallowed again.

For a pane whose purpose is "press a button to record a decision", every first press looks like "nothing happened". We shipped a visible "pane focused…" notice as a workaround, but it does not solve it.

**What I expected**
`ButtonProps` docs say a click raises `ui.press`:

> "a click, a `hotkey`, the chord for its `action`, or Enter under the focus raises `ui.press`, its bottom `onPress`."

I expected the click that gives the pane the keyboard to also press the Button under the cursor, as a browser does: focus moves and the click lands.

**What the docs say about focus (claude-code.d.ts, 2.1.299)**
- `hotkey`: "Its site holds it after ctrl+x tab, a click or `open({ focus })`: the band or its `Pane`; never the composer…" — so a click is documented as a way to take the focus, but nothing says the click is consumed by that.
- `autoFocus`: "A pane opened with `focus`, or the person's focus chord or click, is the take."
- `Client.onKey`: "reached while a click has given it the focus; Escape returns that."
- `$.ui.open({ focus: true })` keeps the keyboard in the pane, but then typing no longer goes to the composer, which is not acceptable for a side pane that lives next to the chat.

**Minimal reproduction (hooks module)**

```tsx
import type { Register } from 'claude-code'

export const register: Register = (on, options) => {
  on('session.start', async ($, e, next) => {
    await $.ui.open({ id: 'click-test', title: 'Click test' })
    return next(e)
  })
  on('ui.render', { component: 'Pane', requestId: 'click-test' }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    return (
      <Box>
        <Text>Click the button once while the cursor is in the prompt field.</Text>
        <Button label="press" onPress={() => $.ui.toast('pressed ' + Date.now())} />
      </Box>
    )
  })
}
```

Steps:
1. Load the plugin in Claude Desktop (Code tab), open a session: the pane appears.
2. Click into the prompt field, so the composer holds the keyboard.
3. Click the `press` button once.

Actual: no toast; the pane now holds the focus. Click again → toast appears.
Expected: toast on the first click.

**Impact**
Any decision/approval pane built with `Button` needs two clicks per action after every message typed. Users read the first click as "the button is broken". Hotkeys only work once the pane already holds the keyboard, so they do not help for the first interaction.

**Ask**
Either (a) deliver the click that gives a pane the focus to the element under the cursor as well, or (b) add a pane/open option such as `clickThrough: true` / `pressOnFocusClick`, or (c) document that a pane without `focus` always needs a focusing click first, so plugins can design around it.

Happy to test a fix build on this machine.
