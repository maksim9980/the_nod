# A driver demo on the fake agent: a brief with a fork, the owner's answer, runs, acceptance.
# Run from any folder: pwsh -File tests/demo-driver.ps1
# No model is called: the manifest commands are tests/fake_agent.py. The repo and its origin live in $env:TEMP.

$ErrorActionPreference = 'Stop'

$Nod = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Fake = Join-Path $PSScriptRoot 'fake_agent.py'
$Python = (Get-Command python).Source
$MaxPasses = 20

$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Folder = Join-Path $env:TEMP "nod-demo-driver-$Stamp"
$Origin = Join-Path $env:TEMP "nod-demo-driver-$Stamp-origin.git"

# The package comes from the Nod working copy; -P keeps files of the current folder from replacing it.
$env:PYTHONPATH = $Nod

function Run-Nod {
    $out = & $Python -P -m the_nod --root $Folder @args
    if ($LASTEXITCODE -ne 0) { throw "nod $args exited with code $LASTEXITCODE" }
    return $out
}

function Run-Git {
    & git -C $Folder @args | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "git $args exited with code $LASTEXITCODE" }
}

function Show-Status {
    Write-Output '--- nod status'
    Run-Nod status --peek | ForEach-Object { Write-Output "    $_" }
}

# Passes until the driver says "idle:".
function Run-Passes {
    for ($n = 1; $n -le $MaxPasses; $n++) {
        $line = ("" + (Run-Nod driver once)).Trim()
        Write-Output "=== pass ${n}: $line"
        Show-Status
        if ($line.StartsWith('idle:')) { return }
    }
    throw "the driver did not reach idle: in $MaxPasses passes"
}

& git init -q --bare -b work $Origin
if ($LASTEXITCODE -ne 0) { throw "git init --bare exited with code $LASTEXITCODE" }
New-Item -ItemType Directory -Path $Folder | Out-Null

Run-Git init -q -b work
Run-Git config user.name 'Demo'
Run-Git config user.email 'demo@example.com'
Run-Git remote add origin $Origin
Set-Content -LiteralPath (Join-Path $Folder 'README.md') -Value '# Tidepool: a Nod driver demo'
Run-Git add README.md
Run-Git commit -q -m 'chore: first commit of the demo repo'
Run-Git push -q origin work

Run-Nod init | Out-Null
Run-Git add .gitignore
Run-Git commit -q -m 'chore: driver files outside git'

# Commands as in tests/driver_helpers.fake: python and the script in quotes, a literal TOML string.
function Fake([string]$Mode) { return "`"$Python`" `"$Fake`" --mode $Mode" }
$Manifest = @"
adapter = "default"
driver_host = ""
[commands]
brief = '$(Fake 'brief-forks-then-ok')'
run = '$(Fake 'run-ok')'
accept = '$(Fake 'accept-ok')'
"@
Set-Content -LiteralPath (Join-Path $Folder '.nod\harness.toml') -Value $Manifest -Encoding utf8NoBOM
Run-Git add .nod/harness.toml
Run-Git commit -q -m 'state: harness on the fake agent'
Run-Git push -q origin work

$id1 = ("" + (Run-Nod card add 'Export habits to CSV')).Trim()
$id2 = ("" + (Run-Nod card add 'Weekly email digest')).Trim()
$id3 = ("" + (Run-Nod card add 'Dark mode for the habit grid')).Trim()
Write-Output "Demo repo: $Folder"
Write-Output "Cards: $id1, $id2, $id3"

Run-Passes

$forks = (Run-Nod --json decision list | Out-String | ConvertFrom-Json) | Where-Object { $_.kind -eq 'fork' }
foreach ($fork in $forks) {
    Write-Output "--- nod decision answer $($fork.id) no"
    Run-Nod decision answer $fork.id 'no' | Out-Null
}

Run-Passes

$cards = Get-ChildItem -LiteralPath (Join-Path $Folder '.nod\cards') -Filter '*.md'
$waiting = @($cards | Where-Object { (Get-Content -LiteralPath $_.FullName -Raw) -match 'status = "waiting-verdict"' })
Write-Output "Waiting for a verdict: $($waiting.Count) of $($cards.Count)"
if ($waiting.Count -ne $cards.Count) { throw 'not every card reached waiting-verdict' }
