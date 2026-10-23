# Contributing to Nod

This file explains how to set up a checkout, which checks to run, and what a change has to follow. Bugs and feature requests go to the [issue tracker](https://github.com/maksim9980/the_nod/issues). Security problems go through the private route in [SECURITY.md](SECURITY.md). Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).

## Set up a checkout

You need Python 3.13 or newer and git.

```
git clone https://github.com/maksim9980/the_nod
cd the_nod
python -m pip install -e .
python -m pip install pytest
```

## Run the checks

Core tests, from the repository root:

```
python -m pytest -q
```

The full run takes about 15 minutes on Windows. While you work, run the file that covers your change, for example `python -m pytest -q tests/test_harness.py`, and run the full suite before you open a pull request.

On Windows with a Cyrillic OEM code page, `test_shim_runs_with_spaces[spaces-and-cyrillic]` fails under `chcp 65001`; `[spaces]` also fails there if the temp or Python path has non-ASCII characters. Run the suite with the default OEM code page.

The Claude Code plugin (the pane, `/nod`, and the MCP server) has its own checks. They need Claude Code installed. CI skips them when `claude` is not on its PATH, so run both from the repository root before you send a change to `mod/`, `hooks/` or `.claude-plugin/`:

```
claude plugin test .
claude plugin validate .
```

## Rules

- `the_nod` uses the Python standard library only. pytest is for tests.
- Comments, docstrings, and text inside code are in English. Russian text lives only in the Russian dictionaries and prompts.
- A new line of interface text needs a key in both dictionaries, `the_nod/i18n/en/` and `the_nod/i18n/ru/`, with the same placeholders. `tests/test_i18n.py` fails when the two differ. The pane has its own pair: `mod/nod-pane/hooks/texts/en.ts` and `mod/nod-pane/hooks/texts/ru.ts`.
- A change to an agent prompt goes into both `the_nod/prompts/default/en/` and `the_nod/prompts/default/ru/`.
- Values written to `.nod/` files and accepted as CLI arguments (decision answers, acceptance results, statuses of review suggestions) are English identifiers defined as constants in `the_nod/vocab.py`. Do not write them inline.
- Test fixtures and examples use the made-up project Tidepool, a habit tracker. Do not put real names, paths, or machine names into tests or docs.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`, then a short description.

## Pull requests

Describe what changed and why, and how you checked it. The pull request template has a checklist. A change that alters behavior comes with tests for that behavior.

By contributing, you agree that your contribution is licensed under the [MIT License](LICENSE) of this repository.
