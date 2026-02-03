# atuin.ps1 - Install Atuin shell history manager

. "$PSScriptRoot\..\lib\common.ps1"

$script:AtuinConfigDir = "$PSScriptRoot\..\configs\atuin"
$script:AtuinDestConfigDir = "$env:USERPROFILE\.config\atuin"

function Test-Atuin {
    try {
        $null = Get-Command atuin -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Install-Atuin {
    <#
    .SYNOPSIS
        Installs Atuin via winget and copies config
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking Atuin..." "INFO"

    # Install Atuin
    if (-not (Test-Atuin) -or $Force) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would install Atuin via winget" "INFO"
        } else {
            $result = Install-WingetPackage -PackageId "Atuinsh.Atuin" -Name "Atuin" -Force:$Force

            if (-not $result) {
                Write-SetupLog "Failed to install Atuin" "ERROR"
                return $false
            }

            Refresh-EnvironmentPath
        }
    } else {
        $version = atuin --version 2>$null
        Write-SetupLog "Atuin is already installed ($version)" "SUCCESS"
    }

    # Copy config
    $configFile = "$script:AtuinConfigDir\config.toml"
    $destConfig = "$script:AtuinDestConfigDir\config.toml"

    if (Test-Path $configFile) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would copy Atuin config to $destConfig" "INFO"
        } else {
            # Create config directory
            if (-not (Test-Path $script:AtuinDestConfigDir)) {
                New-Item -ItemType Directory -Path $script:AtuinDestConfigDir -Force | Out-Null
            }

            Copy-ConfigFile -Source $configFile -Destination $destConfig -Force:$Force
        }
    } else {
        Write-SetupLog "Config file not found: $configFile" "WARNING"
    }

    Write-SetupLog "Atuin setup complete" "SUCCESS"
    return $true
}

function Uninstall-Atuin {
    param(
        [switch]$RemoveConfig
    )

    Write-SetupLog "Uninstalling Atuin..." "INFO"
    Start-Process -FilePath "winget" -ArgumentList "uninstall --id Atuinsh.Atuin --silent --disable-interactivity" -Wait -WindowStyle Hidden

    if ($RemoveConfig -and (Test-Path $script:AtuinDestConfigDir)) {
        Remove-Item -Path $script:AtuinDestConfigDir -Recurse -Force
        Write-SetupLog "Removed Atuin config directory" "SUCCESS"
    }

    Write-SetupLog "Atuin uninstalled" "SUCCESS"
}
