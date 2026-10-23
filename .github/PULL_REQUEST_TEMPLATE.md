## What and why

<!-- What does this change, and what problem does it solve? Link the issue if there is one. -->

## How it was checked

<!-- Commands you ran, and what you saw. -->

## Checklist

- [ ] Core tests pass: `python -m pytest -q`
- [ ] Plugin checks pass if the change touches `mod/`, `hooks/` or `.claude-plugin/`: `claude plugin test .` and `claude plugin validate .`
- [ ] New or changed text exists in both languages (`en` and `ru`): interface dictionaries, mod dictionaries, prompts
- [ ] Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`)
