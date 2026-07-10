# yazi.ps1 - Install yazi terminal file manager

. "$PSScriptRoot\..\lib\common.ps1"

$script:YaziConfigDir     = "$PSScriptRoot\..\configs\yazi"
$script:YaziDestConfigDir = "$env:APPDATA\yazi"

function Test-Yazi {
    try {
        $null = Get-Command yazi -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Install-Yazi {
    <#
    .SYNOPSIS
        Installs yazi via winget and copies config
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking yazi..." "INFO"

    if (-not (Test-Yazi) -or $Force) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would install yazi via winget" "INFO"
        } else {
            $result = Install-WingetPackage -PackageId "sxyazi.yazi" -Name "yazi" -Force:$Force

            if (-not $result) {
                Write-SetupLog "Failed to install yazi" "ERROR"
                return $false
            }

            Refresh-EnvironmentPath
        }
    } else {
        Write-SetupLog "yazi is already installed" "SUCCESS"
    }

    # Copy config directory
    if (Test-Path $script:YaziConfigDir) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would copy yazi config to $script:YaziDestConfigDir" "INFO"
        } else {
            Copy-ConfigDirectory -Source $script:YaziConfigDir -Destination $script:YaziDestConfigDir -Force:$Force | Out-Null
        }
    } else {
        Write-SetupLog "Config directory not found: $script:YaziConfigDir" "WARNING"
    }

    Write-SetupLog "yazi setup complete" "SUCCESS"
    return $true
}

function Uninstall-Yazi {
    param(
        [switch]$RemoveConfig
    )

    Write-SetupLog "Uninstalling yazi..." "INFO"
    Start-Process -FilePath "winget" -ArgumentList "uninstall --id sxyazi.yazi --silent --disable-interactivity" -Wait -WindowStyle Hidden

    if ($RemoveConfig -and (Test-Path $script:YaziDestConfigDir)) {
        Remove-Item -Path $script:YaziDestConfigDir -Recurse -Force
        Write-SetupLog "Removed yazi config directory" "SUCCESS"
    }

    Write-SetupLog "yazi uninstalled" "SUCCESS"
}
