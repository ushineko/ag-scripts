# glow.ps1 - Install glow markdown renderer

. "$PSScriptRoot\..\lib\common.ps1"

$script:GlowConfigDir     = "$PSScriptRoot\..\configs\glow"
$script:GlowDestConfigDir = "$env:APPDATA\glow"

function Test-Glow {
    try {
        $null = Get-Command glow -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Install-Glow {
    <#
    .SYNOPSIS
        Installs glow via winget and copies config
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking glow..." "INFO"

    if (-not (Test-Glow) -or $Force) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would install glow via winget" "INFO"
        } else {
            $result = Install-WingetPackage -PackageId "charmbracelet.glow" -Name "glow" -Force:$Force

            if (-not $result) {
                Write-SetupLog "Failed to install glow" "ERROR"
                return $false
            }

            Refresh-EnvironmentPath
        }
    } else {
        $version = & glow --version 2>$null | Select-Object -First 1
        Write-SetupLog "glow is already installed ($version)" "SUCCESS"
    }

    # Copy config directory
    if (Test-Path $script:GlowConfigDir) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would copy glow config to $script:GlowDestConfigDir" "INFO"
        } else {
            Copy-ConfigDirectory -Source $script:GlowConfigDir -Destination $script:GlowDestConfigDir -Force:$Force | Out-Null
        }
    } else {
        Write-SetupLog "Config directory not found: $script:GlowConfigDir" "WARNING"
    }

    Write-SetupLog "glow setup complete" "SUCCESS"
    return $true
}

function Uninstall-Glow {
    param(
        [switch]$RemoveConfig
    )

    Write-SetupLog "Uninstalling glow..." "INFO"
    Start-Process -FilePath "winget" -ArgumentList "uninstall --id charmbracelet.glow --silent --disable-interactivity" -Wait -WindowStyle Hidden

    if ($RemoveConfig -and (Test-Path $script:GlowDestConfigDir)) {
        Remove-Item -Path $script:GlowDestConfigDir -Recurse -Force
        Write-SetupLog "Removed glow config directory" "SUCCESS"
    }

    Write-SetupLog "glow uninstalled" "SUCCESS"
}
