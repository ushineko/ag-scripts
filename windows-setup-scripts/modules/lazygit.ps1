# lazygit.ps1 - Install lazygit terminal git UI

. "$PSScriptRoot\..\lib\common.ps1"

$script:LazygitConfigDir     = "$PSScriptRoot\..\configs\lazygit"
# lazygit --print-config-dir returns %LOCALAPPDATA%\lazygit on Windows (the Local
# roaming-state dir, NOT %APPDATA%\Roaming). Verified via `lazygit --print-config-dir`.
$script:LazygitDestConfigDir = "$env:LOCALAPPDATA\lazygit"

function Test-Lazygit {
    try {
        $null = Get-Command lazygit -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Install-Lazygit {
    <#
    .SYNOPSIS
        Installs lazygit via winget and copies config
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking lazygit..." "INFO"

    if (-not (Test-Lazygit) -or $Force) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would install lazygit via winget" "INFO"
        } else {
            $result = Install-WingetPackage -PackageId "JesseDuffield.lazygit" -Name "lazygit" -Force:$Force

            if (-not $result) {
                Write-SetupLog "Failed to install lazygit" "ERROR"
                return $false
            }

            Refresh-EnvironmentPath
        }
    } else {
        Write-SetupLog "lazygit is already installed" "SUCCESS"
    }

    # Copy config directory
    if (Test-Path $script:LazygitConfigDir) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would copy lazygit config to $script:LazygitDestConfigDir" "INFO"
        } else {
            Copy-ConfigDirectory -Source $script:LazygitConfigDir -Destination $script:LazygitDestConfigDir -Force:$Force | Out-Null
        }
    } else {
        Write-SetupLog "Config directory not found: $script:LazygitConfigDir" "WARNING"
    }

    Write-SetupLog "lazygit setup complete" "SUCCESS"
    return $true
}

function Uninstall-Lazygit {
    param(
        [switch]$RemoveConfig
    )

    Write-SetupLog "Uninstalling lazygit..." "INFO"
    Start-Process -FilePath "winget" -ArgumentList "uninstall --id JesseDuffield.lazygit --silent --disable-interactivity" -Wait -WindowStyle Hidden

    if ($RemoveConfig -and (Test-Path $script:LazygitDestConfigDir)) {
        Remove-Item -Path $script:LazygitDestConfigDir -Recurse -Force
        Write-SetupLog "Removed lazygit config directory" "SUCCESS"
    }

    Write-SetupLog "lazygit uninstalled" "SUCCESS"
}
