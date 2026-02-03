# neovim.ps1 - Install Neovim with NvChad configuration

. "$PSScriptRoot\..\lib\common.ps1"

$script:NvimPath = "$env:ProgramFiles\Neovim\bin\nvim.exe"
$script:NvimConfigDir = "$PSScriptRoot\..\configs\nvim"
$script:NvimDestConfigDir = "$env:LOCALAPPDATA\nvim"

function Test-Neovim {
    return Test-Installation -Path $script:NvimPath -ExpectedType "File"
}

function Install-Neovim {
    <#
    .SYNOPSIS
        Installs Neovim via winget and copies NvChad configuration
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking Neovim..." "INFO"

    # Install Neovim
    if (-not (Test-Neovim) -or $Force) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would install Neovim via winget" "INFO"
        } else {
            $result = Install-WingetPackage -PackageId "Neovim.Neovim" -Name "Neovim" -Force:$Force

            if (-not $result) {
                Write-SetupLog "Failed to install Neovim" "ERROR"
                return $false
            }

            Refresh-EnvironmentPath
        }
    } else {
        $version = & $script:NvimPath --version 2>$null | Select-Object -First 1
        Write-SetupLog "Neovim is already installed ($version)" "SUCCESS"
    }

    # Copy NvChad configuration
    if (Test-Path $script:NvimConfigDir) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would copy NvChad config to $script:NvimDestConfigDir" "INFO"
        } else {
            # Check if config already exists
            if (Test-Path $script:NvimDestConfigDir) {
                if (-not $Force) {
                    Write-SetupLog "Neovim config exists (use -Force to overwrite): $script:NvimDestConfigDir" "INFO"
                    # Skip copying, config already exists
                } else {
                    Backup-Item -Path $script:NvimDestConfigDir | Out-Null
                    Remove-Item -Path $script:NvimDestConfigDir -Recurse -Force
                    Copy-Item -Path $script:NvimConfigDir -Destination $script:NvimDestConfigDir -Recurse -Force
                    Write-SetupLog "NvChad configuration copied to $script:NvimDestConfigDir" "SUCCESS"
                    Write-SetupLog "Neovim plugins will be installed on first launch" "INFO"
                }
            } else {
                # No existing config, copy fresh
                Copy-Item -Path $script:NvimConfigDir -Destination $script:NvimDestConfigDir -Recurse -Force
                Write-SetupLog "NvChad configuration copied to $script:NvimDestConfigDir" "SUCCESS"
                Write-SetupLog "Neovim plugins will be installed on first launch" "INFO"
            }
        }
    } else {
        Write-SetupLog "NvChad config not found: $script:NvimConfigDir" "WARNING"
    }

    Write-SetupLog "Neovim setup complete" "SUCCESS"
    return $true
}

function Uninstall-Neovim {
    param(
        [switch]$RemoveConfig
    )

    Write-SetupLog "Uninstalling Neovim..." "INFO"
    Start-Process -FilePath "winget" -ArgumentList "uninstall --id Neovim.Neovim --silent --disable-interactivity" -Wait -WindowStyle Hidden

    if ($RemoveConfig) {
        if (Test-Path $script:NvimDestConfigDir) {
            Remove-Item -Path $script:NvimDestConfigDir -Recurse -Force
            Write-SetupLog "Removed Neovim config directory" "SUCCESS"
        }

        # Also remove lazy.nvim data
        $lazyDir = "$env:LOCALAPPDATA\nvim-data"
        if (Test-Path $lazyDir) {
            Remove-Item -Path $lazyDir -Recurse -Force
            Write-SetupLog "Removed Neovim data directory" "SUCCESS"
        }
    }

    Write-SetupLog "Neovim uninstalled" "SUCCESS"
}
