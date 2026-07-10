#Requires -Version 5.1
<#
  uninstall.ps1 — remove the herdr-resurrect Windows install (mirror of
  uninstall.sh): unregister the two scheduled tasks, delete the launcher, and
  strip the managed block from the pwsh profile. Leaves the config + snapshots
  under %USERPROFILE%\.config\herdr-resurrect unless -Purge is given.
#>
[CmdletBinding()]
param([switch]$Purge)

$ErrorActionPreference = 'Stop'
$App = 'herdr-resurrect'

foreach ($t in "$App-save", "$App-autorestore") {
    if (Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $t -Confirm:$false
        Write-Host "removed task: $t"
    }
}

$Launcher = Join-Path $env:USERPROFILE "bin\$App.cmd"
if (Test-Path $Launcher) { Remove-Item -LiteralPath $Launcher -Force; Write-Host "removed launcher: $Launcher" }

$ProfilePath = $PROFILE.CurrentUserCurrentHost
if (Test-Path $ProfilePath) {
    $beginMark = "# >>> $App autostart >>>"
    $endMark = "# <<< $App autostart <<<"
    $pattern = "(?ms)\r?\n?" + [regex]::Escape($beginMark) + ".*?" + [regex]::Escape($endMark)
    $content = Get-Content -Raw -LiteralPath $ProfilePath
    $cleaned = [regex]::Replace($content, $pattern, '').TrimEnd()
    Set-Content -LiteralPath $ProfilePath -Value ($cleaned + "`r`n") -Encoding utf8
    Write-Host "cleaned profile block: $ProfilePath"
}

# Marker (transient state) — always safe to drop.
$marker = Join-Path $env:LOCALAPPDATA "$App\autorestore-server.marker"
if (Test-Path $marker) { Remove-Item -LiteralPath $marker -Force }

if ($Purge) {
    $cfg = Join-Path $env:USERPROFILE ".config\$App"
    if (Test-Path $cfg) { Remove-Item -LiteralPath $cfg -Recurse -Force; Write-Host "removed config + snapshots ($cfg)" }
}

Write-Host "$App uninstalled."
