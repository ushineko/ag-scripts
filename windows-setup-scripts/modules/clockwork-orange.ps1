# clockwork-orange.ps1 - Install clockwork-orange from GitHub

. "$PSScriptRoot\..\lib\common.ps1"

$script:InstallDir = "$env:LOCALAPPDATA\Programs\clockwork-orange"

function Test-ClockworkOrange {
    # Check for any executable in the install directory
    if (Test-Path $script:InstallDir) {
        $exeFiles = Get-ChildItem -Path $script:InstallDir -Filter "*.exe" -ErrorAction SilentlyContinue
        return $exeFiles.Count -gt 0
    }
    return $false
}

function Install-ClockworkOrange {
    <#
    .SYNOPSIS
        Downloads and installs clockwork-orange from GitHub releases
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking clockwork-orange..." "INFO"

    if ((Test-ClockworkOrange) -and -not $Force) {
        Write-SetupLog "clockwork-orange is already installed at $script:InstallDir" "SUCCESS"
        return $true
    }

    if ($DryRun) {
        Write-SetupLog "[DRY RUN] Would download clockwork-orange from GitHub" "INFO"
        return $true
    }

    $tempDir = "$env:TEMP\clockwork-orange-installer"
    $exePath = "$tempDir\clockwork-orange.exe"

    try {
        # Clean up previous temp files
        if (Test-Path $tempDir) {
            Remove-Item -Path $tempDir -Recurse -Force
        }
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

        # Download from GitHub releases
        Write-SetupLog "Downloading clockwork-orange from GitHub..." "INFO"
        $downloaded = Get-GitHubReleaseAsset -Repo "ushineko/clockwork-orange" -Pattern "clockwork-orange.exe" -OutputPath $exePath

        if (-not $downloaded) {
            Write-SetupLog "Failed to download clockwork-orange. No Windows executable found in releases." "ERROR"
            Write-SetupLog "Please check https://github.com/ushineko/clockwork-orange/releases" "INFO"
            return $false
        }

        # Create install directory
        if (Test-Path $script:InstallDir) {
            if ($Force) {
                Backup-Item -Path $script:InstallDir | Out-Null
                Remove-Item -Path $script:InstallDir -Recurse -Force
            }
        }
        New-Item -ItemType Directory -Path $script:InstallDir -Force | Out-Null

        # Copy executable to install directory
        Copy-Item -Path $exePath -Destination "$script:InstallDir\clockwork-orange.exe" -Force

        # Cleanup
        Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue

        Write-SetupLog "clockwork-orange installed to $script:InstallDir" "SUCCESS"

        # Add to PATH (optional - add to user PATH)
        $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
        if ($userPath -notlike "*$script:InstallDir*") {
            [Environment]::SetEnvironmentVariable("Path", "$userPath;$script:InstallDir", "User")
            Write-SetupLog "Added clockwork-orange to user PATH" "INFO"
        }

        return $true

    } catch {
        Write-SetupLog "Failed to install clockwork-orange: $_" "ERROR"
        return $false
    }
}

function Uninstall-ClockworkOrange {
    Write-SetupLog "Uninstalling clockwork-orange..." "INFO"

    if (Test-Path $script:InstallDir) {
        Remove-Item -Path $script:InstallDir -Recurse -Force
        Write-SetupLog "clockwork-orange removed" "SUCCESS"

        # Remove from PATH
        $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $newPath = ($userPath -split ';' | Where-Object { $_ -ne $script:InstallDir }) -join ';'
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-SetupLog "Removed clockwork-orange from PATH" "INFO"
    } else {
        Write-SetupLog "clockwork-orange is not installed" "INFO"
    }
}
