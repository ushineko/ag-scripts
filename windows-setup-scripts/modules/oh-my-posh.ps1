# oh-my-posh.ps1 - Install Oh My Posh prompt engine

. "$PSScriptRoot\..\lib\common.ps1"

$script:OmpConfigDir = "$PSScriptRoot\..\configs\oh-my-posh"
$script:OmpDestConfigDir = "$env:USERPROFILE\.config\oh-my-posh"
$script:PsProfileSource = "$PSScriptRoot\..\configs\powershell\Microsoft.PowerShell_profile.ps1"

# Get the actual Documents folder using Shell.Application (handles OneDrive redirection)
$shell = New-Object -ComObject Shell.Application
$script:DocumentsFolder = $shell.NameSpace('personal').Self.Path
if (-not $script:DocumentsFolder) {
    $script:DocumentsFolder = "$env:USERPROFILE\Documents"
}

$script:Ps5ProfileDir = "$script:DocumentsFolder\WindowsPowerShell"
$script:Ps7ProfileDir = "$script:DocumentsFolder\PowerShell"

function Test-OhMyPosh {
    try {
        $null = Get-Command oh-my-posh -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Install-OhMyPosh {
    <#
    .SYNOPSIS
        Installs Oh My Posh via winget and copies theme config
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking Oh My Posh..." "INFO"

    # Install Oh My Posh
    if (-not (Test-OhMyPosh) -or $Force) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would install Oh My Posh via winget" "INFO"
        } else {
            $result = Install-WingetPackage -PackageId "JanDeDobbeleer.OhMyPosh" -Name "Oh My Posh" -Force:$Force

            if (-not $result) {
                Write-SetupLog "Failed to install Oh My Posh" "ERROR"
                return $false
            }

            Refresh-EnvironmentPath
        }
    } else {
        $version = oh-my-posh --version 2>$null
        Write-SetupLog "Oh My Posh is already installed (version: $version)" "SUCCESS"
    }

    # Copy theme config
    $themeFile = "$script:OmpConfigDir\powerlevel10k_rainbow.omp.json"
    $destTheme = "$script:OmpDestConfigDir\powerlevel10k_rainbow.omp.json"

    if (Test-Path $themeFile) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would copy Oh My Posh theme to $destTheme" "INFO"
        } else {
            # Create config directory
            if (-not (Test-Path $script:OmpDestConfigDir)) {
                New-Item -ItemType Directory -Path $script:OmpDestConfigDir -Force | Out-Null
            }

            Copy-ConfigFile -Source $themeFile -Destination $destTheme -Force:$Force
        }
    } else {
        Write-SetupLog "Theme file not found: $themeFile" "WARNING"
    }

    # Install PowerShell profile for both PS5 and PS7
    if (Test-Path $script:PsProfileSource) {
        foreach ($profileDir in @($script:Ps5ProfileDir, $script:Ps7ProfileDir)) {
            $destProfile = "$profileDir\Microsoft.PowerShell_profile.ps1"

            if ($DryRun) {
                Write-SetupLog "[DRY RUN] Would copy PowerShell profile to $destProfile" "INFO"
            } else {
                # Create profile directory if needed
                if (-not (Test-Path $profileDir)) {
                    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
                }

                Copy-ConfigFile -Source $script:PsProfileSource -Destination $destProfile -Force:$Force | Out-Null
            }
        }
    } else {
        Write-SetupLog "PowerShell profile source not found: $script:PsProfileSource" "WARNING"
    }

    Write-SetupLog "Oh My Posh setup complete" "SUCCESS"
    return $true
}

function Uninstall-OhMyPosh {
    param(
        [switch]$RemoveConfig
    )

    Write-SetupLog "Uninstalling Oh My Posh..." "INFO"
    Start-Process -FilePath "winget" -ArgumentList "uninstall --id JanDeDobbeleer.OhMyPosh --silent --disable-interactivity" -Wait -WindowStyle Hidden

    if ($RemoveConfig -and (Test-Path $script:OmpDestConfigDir)) {
        Remove-Item -Path $script:OmpDestConfigDir -Recurse -Force
        Write-SetupLog "Removed Oh My Posh config directory" "SUCCESS"
    }

    Write-SetupLog "Oh My Posh uninstalled" "SUCCESS"
}
