# Publishing Nod 0.1.0

These are the steps of the repository owner, in order. Nothing in the repository publishes by itself.

Open a terminal in the repository root, `<path to the_nod>`. Where PowerShell and bash differ, each has its own block; where they do not, one block serves both. Use one terminal window for all the steps. The account name you set in step 1 is used again in steps 3 to 7, and the identity you set in step 2 is used in step 3.

## Before you start

- You have a GitHub account that will own the repository, and a PyPI account with two-factor authentication.
- Git, Python 3.13 or newer, `pipx` and Claude Code (`claude` on PATH) are installed. The GitHub CLI `gh` is optional.
- Everything that goes public is already committed on `release-0.1.0`, including the Reddit image `docs/launch/panel.png`. Step 2 takes the tree of that branch and nothing else.
- You are on `release-0.1.0`, the working tree is clean, and the repository has no remote.

```
git switch release-0.1.0
```

```
git status --short
```

```
git remote -v
```

The last two commands print nothing. This one prints the path of the image:

```
git ls-files docs/launch/panel.png
```

## 1. Set the GitHub account

The files link to the repository with a placeholder in place of the account name. Replace it with the name of the GitHub user or organization that will own the repository. Below, that name is `<account>`.

The placeholder is written with a bracket, `OWNE[R]`, in the commands of this file. The bracket keeps this file from matching its own search and being rewritten.

List the files that hold the placeholder:

```
git grep -lIE "OWNE[R]/the_nod|github\.com/OWNE[R]"
```

Replace it in those files.

PowerShell (7 or Windows PowerShell 5.1). The .NET calls keep UTF-8 without a byte order mark and leave the line endings alone:

```powershell
$account = "<account>"
$utf8 = [System.Text.UTF8Encoding]::new($false)
foreach ($file in git grep -lIE "OWNE[R]/the_nod|github\.com/OWNE[R]") {
    $path = (Resolve-Path -LiteralPath $file).ProviderPath
    $text = [System.IO.File]::ReadAllText($path, $utf8)
    $text = $text -replace "OWNE[R]/the_nod", "$account/the_nod" -replace "github\.com/OWNE[R]", "github.com/$account"
    [System.IO.File]::WriteAllText($path, $text, $utf8)
}
```

bash. On macOS write `sed -i ''` in place of `sed -i`:

```bash
account="<account>"
git grep -lIE "OWNE[R]/the_nod|github\.com/OWNE[R]" | xargs sed -i -e "s#OWNE[R]/the_nod#$account/the_nod#g" -e "s#github\.com/OWNE[R]#github.com/$account#g"
```

Look at what changed:

```
git diff --stat
```

Check that no placeholder is left:

```
git grep -n "OWNE[R]"
```

The only lines it may print are in `tests/test_release_hygiene.py`: they are variable names in code, and the test spells the placeholder in two pieces so that the replacement skips it. Any other line is a placeholder that was missed. Run the replacement again after fixing the cause.

Run the hygiene test:

```
python -m pytest -q tests/test_release_hygiene.py
```

It must pass. The test fails only when a placeholder remains outside the files it knows. It does not need the placeholder to exist, so nothing in it needs editing.

Count the launch drafts again. Your account name now sits in their links, and every character of it counts. The Telegram draft is close to its limit and has your account name in two links, so a long name costs twice its length. The command prints the Telegram count (limit 800) and the count of each X post (limit 280), with links at full length:

```
python -c "import pathlib,re; t=pathlib.Path('docs/launch/telegram-ru.md').read_text(encoding='utf-8').split('\n## ',1)[1].split('\n',1)[1].strip(); print('telegram', len(t), 'of 800'); x=pathlib.Path('docs/launch/x-thread.md').read_text(encoding='utf-8'); [print('x post', n, len(b.strip()), 'of 280') for n,b in re.findall(r'^## (\d+)\n(.*?)(?=^## |\Z)', x, re.S|re.M)]"
```

If a count is over its limit, shorten that draft and run the command again.

Commit:

```
git commit -am "docs: set the GitHub owner"
```

## 2. Squash the history into one commit

This makes one commit that holds the tree of `release-0.1.0` and has no parent. The branch `release-0.1.0` is not touched. A push of `main` sends that one commit and its files. No other commit, branch or message leaves your machine.

Set the name and address that will show in the public history. If you do not want your own address there, use the no-reply address from the email settings of your GitHub account.

PowerShell:

```powershell
$env:GIT_AUTHOR_NAME = "<Name>"; $env:GIT_AUTHOR_EMAIL = "<email>"
$env:GIT_COMMITTER_NAME = $env:GIT_AUTHOR_NAME; $env:GIT_COMMITTER_EMAIL = $env:GIT_AUTHOR_EMAIL
```

bash:

```bash
export GIT_AUTHOR_NAME="<Name>" GIT_AUTHOR_EMAIL="<email>"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
```

Create the commit and the branch `main`. If your clone already has a branch `main`, the branch command overwrites it.

PowerShell. If `git commit-tree` fails, `$sha` stays empty, PowerShell drops the empty argument, and `git branch -f main` would then point `main` at the current history. The check stops that:

```powershell
$sha = git commit-tree "release-0.1.0^{tree}" -m "Initial release"
if (-not $sha) { throw "commit-tree failed" } else { git branch -f main $sha; git switch main }
```

bash:

```bash
sha=$(git commit-tree "release-0.1.0^{tree}" -m "Initial release")
test -n "$sha" && git branch -f main "$sha" && git switch main
```

Count the commits on `main`. It must print `1`:

```
git rev-list --count main
```

If it prints anything else, stop. Do not push anything. Switch back, delete `main`, and repeat this step from the commit command:

```
git switch release-0.1.0
```

```
git branch -D main
```

Check the rest of the result. The first command prints one line, `Initial release`, with your name and address:

```
git log --format="%h %an <%ae> %s"
```

The second prints nothing, because the two trees are the same:

```
git diff --stat release-0.1.0 main
```

## 3. Create the GitHub repository and push

Create an empty repository named `the_nod`, public, with no README, license or `.gitignore`. Use the GitHub website, or the GitHub CLI after `gh auth login`:

```
gh repo create "$account/the_nod" --public --description "A decision queue for agent-driven development: agents move the project, you only decide."
```

Add the remote and push `main`:

```
git remote add origin "https://github.com/$account/the_nod.git"
```

```
git push -u origin main
```

Tag the release and push the tag:

```
git tag -a v0.1.0 -m "Nod 0.1.0"
```

```
git push origin v0.1.0
```

Push only these two names. Never push the branch `release-0.1.0`, and never use `--all`, `--mirror` or `--tags`.

In the repository settings, turn on private vulnerability reporting (under the security settings). `SECURITY.md`, `CODE_OF_CONDUCT.md` and the issue chooser send people to that form, and it does not exist until you turn it on.

Clear the identity variables.

PowerShell:

```powershell
Remove-Item Env:GIT_AUTHOR_NAME, Env:GIT_AUTHOR_EMAIL, Env:GIT_COMMITTER_NAME, Env:GIT_COMMITTER_EMAIL
```

bash:

```bash
unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
```

## 4. Wait for green CI

Open `https://github.com/<account>/the_nod/actions`. The workflow `CI` runs the core tests on Ubuntu, macOS and Windows. Wait until all three jobs are green. The core tests have not run on macOS yet, and on Linux they ran only under WSL with Python 3.12, so a red job there is possible.

Or watch from the terminal:

```
gh run list --repo "$account/the_nod"
```

If a job is red, stop here and do not go on to PyPI. Fix the cause and commit the fix on `release-0.1.0`. While nobody has cloned the repository, you can redo the squash. Switch back to the branch:

```
git switch release-0.1.0
```

Repeat step 2, which sets the identity again. Then push `main` and the tag again, with force:

```
git push --force-with-lease origin main
```

```
git tag -f -a v0.1.0 -m "Nod 0.1.0"
```

```
git push --force origin v0.1.0
```

Clear the identity variables again, with the commands at the end of step 3.

## 5. Publish to PyPI

Open `https://pypi.org/project/the-nod/`. A 404 page means the name `the-nod` is free. If the page exists, stop: the name is taken.

The first upload registers the name. For that upload, create an API token on PyPI with the scope "Entire account", because a token for one project can only exist after the project does. Right after the upload, create a token for the project `the-nod` and delete the account token.

PyPI never accepts the same version twice, even after a delete. A mistake in `0.1.0` can only be fixed by `0.1.1`.

Install the tools. `build` is not a dependency of Nod:

```
python -m pip install --upgrade build twine
```

If pip answers `externally-managed-environment` (Python from Homebrew, Debian or Ubuntu), install the tools into a virtual environment instead. In the rest of this step, write the Python of that environment in place of `python`: `.\.venv-release\Scripts\python` in PowerShell, `.venv-release/bin/python` in bash (`.venv-release/Scripts/python` in Git Bash on Windows).

PowerShell:

```powershell
python -m venv .venv-release
.\.venv-release\Scripts\python -m pip install --upgrade build twine
```

bash:

```bash
python3 -m venv .venv-release
.venv-release/bin/python -m pip install --upgrade build twine
```

Delete the folder `.venv-release` after the upload.

Build from the checkout on `main`, so that the files match the tag:

```
python -m build
```

The folder `dist/` now holds one `.tar.gz` and one `.whl`, both with `0.1.0` in the name. Check them:

```
python -m twine check dist/*
```

Both files must report `PASSED`.

Optional dry run on TestPyPI. It needs its own account and token at `https://test.pypi.org`. Twine asks for a password: paste the TestPyPI token:

```
python -m twine upload --repository testpypi -u __token__ dist/*
```

Upload to PyPI. Twine asks for a password: paste the token, which starts with `pypi-`. Do not save it in a file of the repository.

```
python -m twine upload -u __token__ dist/*
```

## 6. Check the installs

Plugin, in a clean profile. An empty config folder makes Claude Code start with no settings, so the check cannot see anything from your own profile.

PowerShell:

```powershell
$profileDir = Join-Path ([System.IO.Path]::GetTempPath()) "nod-clean-profile"
New-Item -ItemType Directory -Force $profileDir | Out-Null
$env:CLAUDE_CONFIG_DIR = $profileDir
claude plugin install nod --marketplace "$account/the_nod"
claude plugin list
```

bash:

```bash
export CLAUDE_CONFIG_DIR="$(mktemp -d)"
claude plugin install nod --marketplace "$account/the_nod"
claude plugin list
```

The list must show `nod`, enabled, with version `0.1.0`. The install may say that two plugin options are not set yet. They have defaults, so ignore the message. Remove the clean profile.

PowerShell:

```powershell
Remove-Item Env:CLAUDE_CONFIG_DIR
Remove-Item -Recurse -Force $profileDir
```

bash:

```bash
rm -rf "${CLAUDE_CONFIG_DIR:?}"
unset CLAUDE_CONFIG_DIR
```

Package, from PyPI. The new version can take a minute to appear, so repeat the first command if it finds nothing. `pipx` needs Python 3.13 or newer; if its default Python is older, add `--python python3.13`.

```
pipx install the-nod
```

```
nod --help
```

The second command prints a line that starts with `usage: nod`.

## 7. Optional: GitHub release and announcements

GitHub release. On the repository page open Releases, then Draft a new release, choose the tag `v0.1.0`, and name it `Nod 0.1.0`. For the text, copy the section `## [0.1.0]` of `CHANGELOG.md`, from `First release.` to the last bullet. With the GitHub CLI, save that text in a file outside the repository and pass its path:

```
gh release create v0.1.0 --repo "$account/the_nod" --title "Nod 0.1.0" --notes-file "<path to the notes file>"
```

The files in `docs/launch/` are drafts. Post them by hand, and only after steps 4 to 6 are green, because every post links to the repository and tells people how to install. Read each draft once more before you post it.

- `docs/launch/show-hn.md`: Hacker News. Plain text, no Markdown, no image.
- `docs/launch/reddit-claudeai.md`: r/ClaudeAI. This is the one post with an image: attach `docs/launch/panel.png`, which is already in the tree, since Reddit takes no SVG. The draft has a caption that says the picture is a drawn mock-up. Check the subreddit rules for project posts on the day.
- `docs/launch/x-thread.md`: X, seven posts, each within the limit counted in step 1.
- `docs/launch/habr-ru.md`: Habr, a Russian article. Pick the hubs named at the top of the draft.
- `docs/launch/telegram-ru.md`: Telegram, within the limit counted in step 1.

## After publishing

The local branch `release-0.1.0` holds the detailed work history. Keep it if you want that history. Never push it.

Deleting it is optional. Only the reflog can bring it back, and only for a while. It also removes the redo path of step 4, so delete it only when you no longer need that path:

```
git branch -D release-0.1.0
```

`git remote -v` must show only `origin`.
