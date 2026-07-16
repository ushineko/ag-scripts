# drag-translucency.ps1 - Auto-translucent windows while dragging (AutoHotkey v2)
#
# Installs the AutoHotkey v2 runtime, deploys drag-translucency.ahk to a stable
# location decoupled from the repo checkout, and registers it to run at login via
# a user Startup-folder shortcut.

. "$PSScriptRoot\..\lib\common.ps1"

$script:AhkPackageId = "AutoHotkey.AutoHotkey"
$script:ConfigSrcDir = "$PSScriptRoot\..\configs\drag-translucency"
$script:ScriptName   = "drag-translucency.ahk"
$script:DestDir      = "$env:LOCALAPPDATA\drag-translucency"

function Get-AutoHotkeyV2Exe {
    # winget's AutoHotkey.AutoHotkey installs v2 to Program Files by default;
    # fall back to the per-user location some installs use. Returns $null if absent.
    $candidates = @(
        "$env:ProgramFiles\AutoHotkey\v2\AutoHotkey64.exe",
        "$env:ProgramFiles\AutoHotkey\v2\AutoHotkey32.exe",
        "$env:LOCALAPPDATA\Programs\AutoHotkey\v2\AutoHotkey64.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}

function Test-DragTranslucency {
    $lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'drag-translucency.lnk'
    return (Test-Path $lnk) -and (Test-Path (Join-Path $script:DestDir $script:ScriptName))
}

function Install-DragTranslucency {
    <#
    .SYNOPSIS
        Installs AutoHotkey v2, deploys the drag-translucency script, and sets it
        to run at login.
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking drag-translucency..." "INFO"

    # 1. AutoHotkey v2 runtime
    if (-not (Get-AutoHotkeyV2Exe)) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would install AutoHotkey v2 via winget" "INFO"
        } else {
            $ok = Install-WingetPackage -PackageId $script:AhkPackageId -Name "AutoHotkey v2" -Force:$Force
            if (-not $ok) {
                Write-SetupLog "Failed to install AutoHotkey v2" "ERROR"
                return $false
            }
            Refresh-EnvironmentPath
        }
    } else {
        Write-SetupLog "AutoHotkey v2 is already installed" "SUCCESS"
    }

    $src = Join-Path $script:ConfigSrcDir $script:ScriptName
    $dst = Join-Path $script:DestDir $script:ScriptName

    if ($DryRun) {
        Write-SetupLog "[DRY RUN] Would deploy $src -> $dst and create a Startup shortcut" "INFO"
        return $true
    }

    if (-not (Test-Path $src)) {
        Write-SetupLog "Script not found: $src" "ERROR"
        return $false
    }

    # 2. Deploy the .ahk to a stable location (Copy-ConfigFile logs a warning and
    #    leaves the existing copy in place when it exists without -Force).
    Copy-ConfigFile -Source $src -Destination $dst -Force:$Force | Out-Null
    if (-not (Test-Path $dst)) {
        Write-SetupLog "drag-translucency script was not deployed" "ERROR"
        return $false
    }

    # 3. Startup-folder shortcut -> AutoHotkey64.exe "<dst>" (idempotent overwrite)
    $ahk = Get-AutoHotkeyV2Exe
    if (-not $ahk) {
        Write-SetupLog "AutoHotkey v2 executable not found after install" "ERROR"
        return $false
    }

    $lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'drag-translucency.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($lnk)
    $shortcut.TargetPath       = $ahk
    $shortcut.Arguments        = "`"$dst`""
    $shortcut.WorkingDirectory = $script:DestDir
    $shortcut.Description       = "Auto-translucent windows while dragging"
    $shortcut.Save()
    Write-SetupLog "Startup shortcut created: $lnk" "SUCCESS"

    Write-SetupLog "drag-translucency setup complete" "SUCCESS"
    return $true
}

function Uninstall-DragTranslucency {
    param(
        [switch]$RemoveConfig
    )

    Write-SetupLog "Uninstalling drag-translucency..." "INFO"

    $lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'drag-translucency.lnk'
    if (Test-Path $lnk) {
        Remove-Item -Path $lnk -Force
        Write-SetupLog "Removed Startup shortcut" "SUCCESS"
    }

    if ($RemoveConfig -and (Test-Path $script:DestDir)) {
        Remove-Item -Path $script:DestDir -Recurse -Force
        Write-SetupLog "Removed deployed drag-translucency script" "SUCCESS"
    }

    # The AutoHotkey v2 runtime is left installed; it may be used by other scripts.
    Write-SetupLog "drag-translucency uninstalled" "SUCCESS"
}
