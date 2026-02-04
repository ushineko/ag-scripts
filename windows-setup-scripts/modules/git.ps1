# git.ps1 - Install Git for Windows

. "$PSScriptRoot\..\lib\common.ps1"

$script:GitPath = "$env:ProgramFiles\Git\cmd\git.exe"
$script:WindowsSshPath = "C:/Windows/System32/OpenSSH/ssh.exe"

function Test-GitForWindows {
    return Test-Installation -Path $script:GitPath -ExpectedType "File"
}

function Set-GitSshCommand {
    <#
    .SYNOPSIS
        Configures git to use Windows OpenSSH
    .DESCRIPTION
        Sets core.sshCommand to use Windows native OpenSSH, which integrates
        with the Windows ssh-agent service for key management.
    #>
    param(
        [switch]$DryRun
    )

    $currentSsh = & $script:GitPath config --global --get core.sshCommand 2>$null

    if ($currentSsh -eq $script:WindowsSshPath) {
        Write-SetupLog "Git is already configured to use Windows OpenSSH" "SUCCESS"
        return
    }

    if ($DryRun) {
        Write-SetupLog "[DRY RUN] Would configure git to use Windows OpenSSH" "INFO"
        return
    }

    try {
        & $script:GitPath config --global core.sshCommand $script:WindowsSshPath
        Write-SetupLog "Git configured to use Windows OpenSSH" "SUCCESS"
    } catch {
        Write-SetupLog "Failed to configure git SSH command: $_" "WARNING"
    }
}

function Set-GitUserConfig {
    <#
    .SYNOPSIS
        Prompts for and configures git user.name and user.email if not already set
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    # Check current config
    $currentName = & $script:GitPath config --global --get user.name 2>$null
    $currentEmail = & $script:GitPath config --global --get user.email 2>$null

    # Handle user.name
    if ([string]::IsNullOrWhiteSpace($currentName) -or $Force) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would prompt for git user.name" "INFO"
        } else {
            Write-Host ""
            if ([string]::IsNullOrWhiteSpace($currentName)) {
                Write-Host "Git user.name is not configured." -ForegroundColor Yellow
            } else {
                Write-Host "Current git user.name: $currentName" -ForegroundColor Cyan
            }
            $newName = Read-Host "Enter your name for git commits (or press Enter to skip)"

            if (-not [string]::IsNullOrWhiteSpace($newName)) {
                & $script:GitPath config --global user.name $newName
                Write-SetupLog "Git user.name set to: $newName" "SUCCESS"
            } elseif ([string]::IsNullOrWhiteSpace($currentName)) {
                Write-SetupLog "Git user.name not configured (skipped)" "WARNING"
            }
        }
    } else {
        Write-SetupLog "Git user.name is already set: $currentName" "SUCCESS"
    }

    # Handle user.email
    if ([string]::IsNullOrWhiteSpace($currentEmail) -or $Force) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would prompt for git user.email" "INFO"
        } else {
            Write-Host ""
            if ([string]::IsNullOrWhiteSpace($currentEmail)) {
                Write-Host "Git user.email is not configured." -ForegroundColor Yellow
            } else {
                Write-Host "Current git user.email: $currentEmail" -ForegroundColor Cyan
            }
            $newEmail = Read-Host "Enter your email for git commits (or press Enter to skip)"

            if (-not [string]::IsNullOrWhiteSpace($newEmail)) {
                & $script:GitPath config --global user.email $newEmail
                Write-SetupLog "Git user.email set to: $newEmail" "SUCCESS"
            } elseif ([string]::IsNullOrWhiteSpace($currentEmail)) {
                Write-SetupLog "Git user.email not configured (skipped)" "WARNING"
            }
        }
    } else {
        Write-SetupLog "Git user.email is already set: $currentEmail" "SUCCESS"
    }
}

function Install-GitForWindows {
    <#
    .SYNOPSIS
        Installs Git for Windows via winget and configures SSH and user settings
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking Git for Windows..." "INFO"

    $wasInstalled = Test-GitForWindows

    if ($wasInstalled -and -not $Force) {
        $version = & $script:GitPath --version 2>$null
        Write-SetupLog "Git for Windows is already installed ($version)" "SUCCESS"
    } else {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would install Git for Windows via winget" "INFO"
        } else {
            $result = Install-WingetPackage -PackageId "Git.Git" -Name "Git for Windows" -Force:$Force

            if (-not $result) {
                return $false
            }

            Refresh-EnvironmentPath
            Write-SetupLog "Git for Windows installed successfully" "SUCCESS"
        }
    }

    # Configure git to use Windows OpenSSH (always check, even if git was already installed)
    if (Test-GitForWindows) {
        Set-GitSshCommand -DryRun:$DryRun

        # Configure user.name and user.email
        Set-GitUserConfig -DryRun:$DryRun -Force:$Force
    }

    return $true
}

function Uninstall-GitForWindows {
    Write-SetupLog "Uninstalling Git for Windows..." "INFO"
    Start-Process -FilePath "winget" -ArgumentList "uninstall --id Git.Git --silent --disable-interactivity" -Wait -WindowStyle Hidden
    Write-SetupLog "Git for Windows uninstalled" "SUCCESS"
}
