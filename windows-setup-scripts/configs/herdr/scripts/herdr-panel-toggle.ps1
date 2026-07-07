# herdr-panel-toggle.ps1 — Windows port of herdr-panel-toggle.sh
#
# Toggle lazygit / yazi side panels in the current herdr tab.
#   herdr-panel-toggle.ps1 both      (default) lazygit right + yazi under main
#   herdr-panel-toggle.ps1 lazygit   lazygit only, full-height on the right
#   herdr-panel-toggle.ps1 yazi      yazi only, under the main area (+ usage strip)
#
# Stateless: panels are identified by pane label (panel:lazygit / panel:yazi /
# panel:usage) via `herdr pane list`, so there is nothing to track between runs.
# Splitting the main pane RIGHT first then DOWN makes lazygit full-height and
# yazi sit under the main column only. A thin Claude-usage strip (--tui) is
# carved off the bottom of the yazi pane.
#
# Not yet ported from Linux: the yazi --client-id / yazi-here addressing.
# --ratio is the share KEPT by the original pane, so the panel gets (1 - ratio).

param([string]$Mode = 'both')
$ErrorActionPreference = 'Stop'

# Resolve the herdr binary. herdr exports HERDR_BIN_PATH into keybound command
# environments; fall back to the known install path when run by hand.
$herdr = if ($env:HERDR_BIN_PATH -and (Test-Path $env:HERDR_BIN_PATH)) { $env:HERDR_BIN_PATH }
         else { "$env:LOCALAPPDATA\Programs\Herdr\bin\herdr.exe" }

function HerdrJson { (& $herdr @args | Out-String | ConvertFrom-Json) }

$LAZY_LABEL      = 'panel:lazygit'
$YAZI_LABEL      = 'panel:yazi'
$USAGE_LABEL     = 'panel:usage'
$LAZY_MAIN_KEEP  = '0.76'   # main keeps 76% width  -> lazygit ~24% on the right
$YAZI_MAIN_KEEP  = '0.70'   # main keeps 70% height -> yazi ~30% underneath
$USAGE_YAZI_KEEP = '0.80'   # yazi keeps 80% height -> usage strip ~20% at bottom

# Claude usage --tui strip (Qt-free, rich-rendered single line). Run from the
# widget repo with the miniforge interpreter that has rich/structlog installed
# (pinned by full path so PATH order in the pane does not matter).
$WIDGET_DIR = "$env:USERPROFILE\git\ag-scripts\claude-usage-widget-windows"
$PYTHON     = if (Test-Path 'C:\miniforge3\python.exe') { 'C:\miniforge3\python.exe' } else { 'python' }
$USAGE_CMD  = "$PYTHON -m src.main --tui"

$cur     = HerdrJson pane current
$tab     = $cur.result.pane.tab_id
$focused = $cur.result.pane.pane_id
$panes   = HerdrJson pane list

# label -> pane_id within this tab (null if absent)
function Panel-Id($label) {
    ($panes.result.panes |
        Where-Object { $_.tab_id -eq $tab -and $_.label -eq $label } |
        Select-Object -First 1).pane_id
}

# The pane to split: the focused pane, unless focus is already in a panel —
# then fall back to the first non-panel pane in the tab.
function Main-Pane {
    $lbl = ($panes.result.panes | Where-Object { $_.pane_id -eq $focused }).label
    if ($lbl -like 'panel:*') {
        ($panes.result.panes |
            Where-Object { $_.tab_id -eq $tab -and $_.label -notlike 'panel:*' } |
            Select-Object -First 1).pane_id
    } else { $focused }
}

# Shell cwd of a pane (the project dir), not its foreground_cwd.
function Pane-Cwd($id) {
    ($panes.result.panes | Where-Object { $_.pane_id -eq $id }).cwd
}

function Open-Lazygit($m, $dir) {
    $id = (HerdrJson pane split $m --direction right --ratio $LAZY_MAIN_KEEP --cwd $dir --no-focus).result.pane.pane_id
    & $herdr pane rename $id $LAZY_LABEL | Out-Null
    # Runs in the panel's pwsh shell; close the pane when lazygit exits.
    & $herdr pane run $id "lazygit; & '$herdr' pane close $id" | Out-Null
}

# Carve a thin usage strip off the bottom of the yazi pane; returns its pane_id.
function Open-Usage($y) {
    $id = (HerdrJson pane split $y --direction down --ratio $USAGE_YAZI_KEEP --cwd $WIDGET_DIR --no-focus).result.pane.pane_id
    & $herdr pane rename $id $USAGE_LABEL | Out-Null
    & $herdr pane run $id "$USAGE_CMD; & '$herdr' pane close $id" | Out-Null
    return $id
}

function Open-Yazi($m, $dir) {
    $id = (HerdrJson pane split $m --direction down --ratio $YAZI_MAIN_KEEP --cwd $dir --no-focus).result.pane.pane_id
    & $herdr pane rename $id $YAZI_LABEL | Out-Null
    $uid = Open-Usage $id   # status strip under yazi; carve it before yazi starts
    # When yazi exits, close the usage strip too, then the yazi pane itself.
    & $herdr pane run $id "yazi `"$dir`"; & '$herdr' pane close $uid; & '$herdr' pane close $id" | Out-Null
}

$lazy  = Panel-Id $LAZY_LABEL
$yazi  = Panel-Id $YAZI_LABEL
$usage = Panel-Id $USAGE_LABEL

switch ($Mode) {
    'lazygit' {
        if ($lazy) { & $herdr pane close $lazy | Out-Null }
        else { $m = Main-Pane; Open-Lazygit $m (Pane-Cwd $m) }
    }
    'yazi' {
        if ($yazi) {
            & $herdr pane close $yazi | Out-Null
            if ($usage) { & $herdr pane close $usage | Out-Null }
        } else { $m = Main-Pane; Open-Yazi $m (Pane-Cwd $m) }
    }
    'both' {
        if ($lazy -or $yazi) {
            if ($lazy)  { & $herdr pane close $lazy  | Out-Null }
            if ($yazi)  { & $herdr pane close $yazi  | Out-Null }
            if ($usage) { & $herdr pane close $usage | Out-Null }
        } else {
            $m = Main-Pane; $dir = Pane-Cwd $m
            Open-Lazygit $m $dir   # right first  -> full height
            Open-Yazi    $m $dir   # then down    -> under the main area
        }
    }
    default {
        Write-Error "usage: herdr-panel-toggle.ps1 [lazygit|yazi|both]"
        exit 2
    }
}
