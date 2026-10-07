# herdr-project-tab.ps1 — Windows port of herdr-project-tab.sh
#
# Pick a project directory and open it as a new tab in the current space.
#   herdr-project-tab.ps1 [root]           pick in this pane (run by hand)
#   herdr-project-tab.ps1 -Launch [root]   keybind entry: stage 1
# root defaults to $env:HERDR_PROJECT_ROOT, else ~\git.
#
# Two stages, because a keybound `type = "shell"` command runs detached (cmd.exe
# /d /c, no console), so fzf cannot run from it directly:
#   1. stage 1 (detached): resolve the focused pane's space, create a scratch tab
#      labelled "pick project", and `pane run` stage 2 inside it.
#   2. stage 2 (no -Launch, in a pane with a console): fzf picks -> create the real
#      tab -> close the scratch tab.
# Run by hand from a pane, it is stage 2 with no scratch tab.
#
# Closing the scratch tab kills stage 2 (it runs in that tab's only pane), so it
# must be the LAST statement on every path, after the real tab is created.
#
# Diagnosis: failures raise a herdr notification. Set HERDR_PROJECT_TAB_LOG to a
# file path to capture a trace of both stages.

param(
    [string]$Root,
    [switch]$Launch,   # stage 1: what the keybind passes
    [string]$Workspace,
    [string]$Scratch = '-'   # '-' = no scratch tab to close
)
$ErrorActionPreference = 'Stop'

$herdr = if ($env:HERDR_BIN_PATH -and (Test-Path $env:HERDR_BIN_PATH)) { $env:HERDR_BIN_PATH }
         else { "$env:LOCALAPPDATA\Programs\Herdr\bin\herdr.exe" }
# Absolute paths: keybound commands and panes spawned by a long-running herdr
# server do not see PATH changes made after the server started.
$fzf  = (Get-Command fzf -ErrorAction SilentlyContinue).Source
if (-not $fzf) { $fzf = "$env:LOCALAPPDATA\Microsoft\WinGet\Links\fzf.exe" }
$pwsh = (Get-Process -Id $PID).Path
$self = $PSCommandPath

if (-not $Root) { $Root = if ($env:HERDR_PROJECT_ROOT) { $env:HERDR_PROJECT_ROOT } else { "$env:USERPROFILE\git" } }

# Opt-in trace. Transcripts miss Set-PSDebug output and die with the scratch
# tab, so append plain lines instead.
function Log($msg) {
    if ($env:HERDR_PROJECT_TAB_LOG) {
        Add-Content -LiteralPath $env:HERDR_PROJECT_TAB_LOG "$(Get-Date -Format HH:mm:ss.fff) [$PID] $msg"
    }
}
Log "start launch=$Launch root=$Root ws=$Workspace scratch=$Scratch fzf=$fzf"

function HerdrJson { (& $herdr @args | Out-String | ConvertFrom-Json) }

function Fail($msg) {
    Log "FAIL $msg"
    & $herdr notification show 'herdr-project-tab' --body $msg | Out-Null
    Write-Error $msg -ErrorAction Continue
}

# One line per project: "<marker>`t<label>`t<path>". Depth-1 dirs under the
# root, plus one level inside any <project>.worktrees\ container, labelled
# <project>@<branch>. `*` marks a project that already has a tab in this space.
function Project-Lines($ws) {
    $open = @((HerdrJson tab list --workspace $ws).result.tabs.label)
    foreach ($d in Get-ChildItem -LiteralPath $Root -Directory | Sort-Object Name) {
        if ($d.Name -like '*.worktrees') {
            $proj = $d.Name -replace '\.worktrees$', ''
            $items = Get-ChildItem -LiteralPath $d.FullName -Directory | Sort-Object Name |
                ForEach-Object { [pscustomobject]@{ Label = "$proj@$($_.Name)"; Path = $_.FullName } }
        } else {
            $items = [pscustomobject]@{ Label = $d.Name; Path = $d.FullName }
        }
        foreach ($i in $items) {
            $mark = if ($open -contains $i.Label) { '*' } else { ' ' }
            "$mark`t$($i.Label)`t$($i.Path)"
        }
    }
}

function Close-Scratch { if ($Scratch -ne '-') { & $herdr tab close $Scratch | Out-Null } }

if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    Fail "project root not found: $Root"
    Close-Scratch
    exit 1
}

if ($Launch) {
    # ---- stage 1 (detached) ----
    try {
        $ws = (HerdrJson pane current).result.pane.workspace_id
        $created = HerdrJson tab create --workspace $ws --label 'pick project' --cwd $Root --focus
        $tab  = $created.result.tab.tab_id
        $pane = $created.result.root_pane.pane_id
        $logArg = if ($env:HERDR_PROJECT_TAB_LOG) { "`$env:HERDR_PROJECT_TAB_LOG='$env:HERDR_PROJECT_TAB_LOG'; " } else { '' }
        Log "stage1 scratch tab=$tab pane=$pane"
        & $herdr pane run $pane "$logArg& '$pwsh' -NoProfile -ExecutionPolicy Bypass -File '$self' -Root '$Root' -Workspace $ws -Scratch $tab" | Out-Null
    } catch {
        Fail "stage 1 failed: $_"
        exit 1
    }
    exit 0
}

# ---- stage 2 (in a pane) ----
try {
    if (-not $Workspace) { $Workspace = (HerdrJson pane current).result.pane.workspace_id }
    if (-not (Test-Path $fzf)) { throw "fzf not found (winget install junegunn.fzf)" }

    $sel = Project-Lines $Workspace | & $fzf `
        --delimiter "`t" --with-nth '1,2' --no-sort --reverse `
        --prompt 'project> ' --header '* = already open in this space' `
        --preview 'git -C {3} log --oneline --color=always -n 40' `
        --preview-window 'right,55%'
    Log "fzf exit=$LASTEXITCODE sel=$sel"

    if ($sel) {
        $f = $sel -split "`t"
        & $herdr tab create --workspace $Workspace --cwd $f[2] --label $f[1] --focus | Out-Null
    }
} catch {
    Fail "stage 2 failed: $_"
}
Close-Scratch   # LAST: this kills the pane stage 2 is running in
