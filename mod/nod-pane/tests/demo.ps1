# Creates a demo repository to check the nod-pane pane by hand.
# Run: pwsh mod/nod-pane/tests/demo.ps1 <folder>
param([Parameter(Mandatory = $true)][string]$Folder)

$ErrorActionPreference = 'Stop'

if (Test-Path -LiteralPath $Folder) {
    Write-Error "The folder exists already: $Folder. Remove it or pick another one."
    exit 1
}

# The package comes from the current python; -P keeps files of the repository from replacing it.
function Run-Nod {
    $out = & python -P -m the_nod --root $Folder @args
    if ($LASTEXITCODE -ne 0) { throw "nod $args returned code $LASTEXITCODE" }
    return $out
}

function Run-Git {
    & git -C $Folder @args | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "git $args returned code $LASTEXITCODE" }
}

New-Item -ItemType Directory -Path $Folder | Out-Null
$Folder = (Resolve-Path -LiteralPath $Folder).Path

Run-Git init -q -b work
Run-Git config user.name 'Demo'
Run-Git config user.email 'demo@example.com'
Set-Content -LiteralPath (Join-Path $Folder 'README.md') -Value '# Tidepool demo'
Run-Git add README.md
Run-Git commit -q -m 'chore: first commit of the demo repository'

Run-Nod init | Out-Null
$id1 = ("" + (Run-Nod card add 'Export habits to CSV')).Trim()
$id2 = ("" + (Run-Nod card add 'Weekly email digest')).Trim()
$id3 = ("" + (Run-Nod card add 'Dark mode for the habit grid')).Trim()

Run-Nod decision ask --kind fork --card $id1 `
    --question 'Write dates to the CSV in ISO or in the local format?' `
    --proposed 'ISO' `
    --option 'ISO' --option 'Local format' `
    --reason 'Every spreadsheet reads ISO.' | Out-Null

Run-Nod run start $id2 | Out-Null

# A frame: a 1x1 PNG from base64.
$frame = Join-Path $Folder 'frame.png'
$png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
[IO.File]::WriteAllBytes($frame, [Convert]::FromBase64String($png))

Run-Nod accept $id3 --level 2 --result solved --evidence '3 cards of 3' `
    --frame $frame --caption 'see: the grid in dark mode' | Out-Null

Write-Output "The demo repository is ready: $Folder"
Write-Output "Cards: $id1 (fork), $id2 (in a run), $id3 (waiting for the verdict)"
