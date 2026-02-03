# antigravity.ps1 - Install Antigravity app

. "$PSScriptRoot\..\lib\common.ps1"

$script:AntigravityDir = "$env:LOCALAPPDATA\Programs\Antigravity"
$script:AntigravityExe = "$script:AntigravityDir\Antigravity.exe"

function Test-Antigravity {
    return Test-Installation -Path $script:AntigravityExe -ExpectedType "File"
}

function Install-Antigravity {
    <#
    .SYNOPSIS
        Guides user to install Antigravity IDE manually
    .DESCRIPTION
        Antigravity requires manual download from antigravity.google.
        This function checks if it's installed and provides instructions if not.
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking Antigravity..." "INFO"

    if ((Test-Antigravity) -and -not $Force) {
        $version = & $script:AntigravityExe --version 2>$null | Select-Object -First 1
        Write-SetupLog "Antigravity is already installed ($version)" "SUCCESS"
        return $true
    }

    if ($DryRun) {
        Write-SetupLog "[DRY RUN] Would prompt user to install Antigravity manually" "INFO"
        return $true
    }

    # Antigravity requires manual download
    Write-SetupLog "Antigravity requires manual installation:" "INFO"
    Write-SetupLog "  1. Visit https://antigravity.google" "INFO"
    Write-SetupLog "  2. Download the IDE installer" "INFO"
    Write-SetupLog "  3. Run the installer" "INFO"
    Write-SetupLog "  4. Re-run this script to verify installation" "INFO"

    return $true  # Don't fail the overall install
}

function Uninstall-Antigravity {
    Write-SetupLog "Uninstalling Antigravity..." "INFO"

    if (Test-Path $script:AntigravityDir) {
        # Try to run uninstaller
        $uninstaller = "$script:AntigravityDir\unins000.exe"
        if (Test-Path $uninstaller) {
            Start-Process -FilePath $uninstaller -ArgumentList "/SILENT" -Wait -NoNewWindow
            Write-SetupLog "Antigravity uninstalled" "SUCCESS"
        } else {
            # Manual removal
            Remove-Item -Path $script:AntigravityDir -Recurse -Force
            Write-SetupLog "Antigravity directory removed" "SUCCESS"
        }
    } else {
        Write-SetupLog "Antigravity is not installed" "INFO"
    }
}
