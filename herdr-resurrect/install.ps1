#Requires -Version 5.1
<#
  install.ps1 — Windows installer for herdr-resurrect (the Windows analogue of
  install.sh, whose systemd user timers don't exist here). It:

    1. writes a launcher `%USERPROFILE%\.local\bin\herdr-resurrect.cmd`
       (for interactive use and the herdr `prefix+ctrl+r` keybinding),
    2. registers two per-user scheduled tasks —
         herdr-resurrect-save         : snapshot every N min (N from config),
         herdr-resurrect-autorestore  : at logon, poll for herdr then restore,
    3. adds a one-shot restore trigger to the pwsh profile that fires the first
       time a herdr server starts (covers herdr launched after the poller window;
       see herdr-resurrect-autostart.ps1).

  Idempotent: re-running replaces the tasks, launcher, and profile block in place.
  Requires python and herdr on PATH. Run from pwsh (uses $PROFILE for the pane
  shell's profile path). No admin needed — all tasks are per-user, Interactive.

  Uninstall with .\uninstall.ps1 (add -Purge to also delete config + snapshots).
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$App = 'herdr-resurrect'
$SrcDir = $PSScriptRoot
$Cli = Join-Path $SrcDir 'cli.py'

# --- deps -------------------------------------------------------------------
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) { throw "${App}: python not found on PATH" }
$PyExe = $pyCmd.Source
$PyW = Join-Path (Split-Path $PyExe) 'pythonw.exe'   # console-less, for the tasks
if (-not (Test-Path $PyW)) { $PyW = $PyExe }
if (-not (Get-Command herdr -ErrorAction SilentlyContinue)) {
    throw "${App}: herdr not found on PATH"
}

# --- launcher ---------------------------------------------------------------
# %USERPROFILE%\bin is already on PATH on this host (and holds other .cmd
# launchers), so the bare `herdr-resurrect` resolves without extra PATH edits.
$BinDir = Join-Path $env:USERPROFILE 'bin'
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$Launcher = Join-Path $BinDir "$App.cmd"
"@echo off`r`n`"$PyExe`" `"$Cli`" %*" | Set-Content -LiteralPath $Launcher -Encoding ascii
Write-Host "launcher: $Launcher"

# --- save interval from config (default 5) ----------------------------------
$Interval = 5
try {
    $out = & $PyExe -c "import sys,os;sys.path.insert(0,r'$SrcDir');import config;print(int(config.load().get('save_interval_min',5)))"
    if ($out -match '^\d+$') { $Interval = [int]$out }
} catch { $Interval = 5 }
if ($Interval -lt 1) { $Interval = 5 }

# --- scheduled tasks --------------------------------------------------------
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# save: at logon, then repeat every N minutes (10-year duration ~= indefinite).
$saveAction = New-ScheduledTaskAction -Execute $PyW -Argument "`"$Cli`" save"
$saveTrigger = New-ScheduledTaskTrigger -AtLogOn
$rep = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Minutes $Interval) `
        -RepetitionDuration (New-TimeSpan -Days 3650)).Repetition
$saveTrigger.Repetition = $rep
Register-ScheduledTask -TaskName "$App-save" -Action $saveAction -Trigger $saveTrigger `
    -Principal $principal -Settings $settings -Force `
    -Description "Snapshot running herdr pane programs every $Interval min ($App)" | Out-Null
Write-Host "task:     $App-save (every $Interval min)"

# autorestore: at logon, poll for herdr then relaunch pane programs.
$arAction = New-ScheduledTaskAction -Execute $PyW `
    -Argument "`"$Cli`" autorestore --window 3600 --interval 30"
$arTrigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "$App-autorestore" -Action $arAction -Trigger $arTrigger `
    -Principal $principal -Settings $settings -Force `
    -Description "Poll for herdr after logon, then restore pane programs ($App)" | Out-Null
Write-Host "task:     $App-autorestore (at logon; polls 1h)"

# --- pwsh profile one-shot (fires restore once per herdr server start) -------
$Autostart = Join-Path $SrcDir 'herdr-resurrect-autostart.ps1'
$ProfilePath = $PROFILE.CurrentUserCurrentHost
$profDir = Split-Path $ProfilePath
if (-not (Test-Path $profDir)) { New-Item -ItemType Directory -Force -Path $profDir | Out-Null }

$beginMark = "# >>> $App autostart >>>"
$endMark = "# <<< $App autostart <<<"
$block = @(
    $beginMark
    "# Fire herdr-resurrect once per herdr server start (managed by $App/install.ps1)."
    "`$__hrAutostart = `"$Autostart`""
    "if (`$env:HERDR_ENV -eq '1' -and (Test-Path `$__hrAutostart)) { & `$__hrAutostart }"
    $endMark
) -join "`r`n"

$existing = if (Test-Path $ProfilePath) { Get-Content -Raw -LiteralPath $ProfilePath } else { '' }
# Strip any prior managed block, then append a fresh one.
$pattern = "(?ms)\r?\n?" + [regex]::Escape($beginMark) + ".*?" + [regex]::Escape($endMark)
$cleaned = [regex]::Replace($existing, $pattern, '').TrimEnd()
$new = if ($cleaned) { "$cleaned`r`n`r`n$block`r`n" } else { "$block`r`n" }
Set-Content -LiteralPath $ProfilePath -Value $new -Encoding utf8
Write-Host "profile:  $ProfilePath (autostart block)"

Write-Host ""
Write-Host "$App installed."
Write-Host "  Snapshot now:   $App save"
Write-Host "  Restore now:    $App restore   (preview: --dry-run)"
Write-Host "  After a reboot: auto-restores at logon (poller) and on first herdr start (profile)."
Write-Host "  Config:         $env:USERPROFILE\.config\$App\config.json"
