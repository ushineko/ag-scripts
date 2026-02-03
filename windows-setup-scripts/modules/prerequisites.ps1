# prerequisites.ps1 - Check and install prerequisite tools
# Ensures winget and Node.js are available before other installations

. "$PSScriptRoot\..\lib\common.ps1"

function Test-Winget {
    try {
        $null = Get-Command winget -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Test-NodeJs {
    try {
        $null = Get-Command node -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Install-Prerequisites {
    <#
    .SYNOPSIS
        Checks and installs prerequisites (winget, Node.js)
    .PARAMETER DryRun
        Show what would be done without making changes
    .PARAMETER Force
        Force reinstallation even if already installed
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking prerequisites..." "INFO"

    # Check PowerShell version
    $psVersion = $PSVersionTable.PSVersion
    Write-SetupLog "PowerShell version: $($psVersion.Major).$($psVersion.Minor)" "INFO"

    if ($psVersion.Major -lt 5) {
        Write-SetupLog "PowerShell 5.0 or higher is required" "ERROR"
        return $false
    }

    # Check/install winget
    if (-not (Test-Winget)) {
        Write-SetupLog "winget is not installed" "WARNING"

        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would prompt to install winget from Microsoft Store" "INFO"
        } else {
            Write-SetupLog "Please install 'App Installer' from the Microsoft Store to get winget" "ERROR"
            Write-SetupLog "URL: https://www.microsoft.com/store/productId/9NBLGGH4NNS1" "INFO"
            return $false
        }
    } else {
        $wingetVersion = (winget --version 2>$null) -replace 'v', ''
        Write-SetupLog "winget is available (version: $wingetVersion)" "SUCCESS"
    }

    # Check/install Node.js
    if (-not (Test-NodeJs) -or $Force) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would install Node.js LTS via winget" "INFO"
            return $true
        }

        Write-SetupLog "Installing Node.js LTS..." "INFO"
        $result = Install-WingetPackage -PackageId "OpenJS.NodeJS.LTS" -Name "Node.js LTS" -Force:$Force

        if (-not $result) {
            Write-SetupLog "Failed to install Node.js" "ERROR"
            return $false
        }

        # Refresh PATH to pick up npm
        Refresh-EnvironmentPath
    } else {
        $nodeVersion = (node --version 2>$null)
        $npmVersion = (npm --version 2>$null)
        Write-SetupLog "Node.js is available (node: $nodeVersion, npm: $npmVersion)" "SUCCESS"
    }

    Write-SetupLog "Prerequisites check complete" "SUCCESS"
    return $true
}

function Uninstall-Prerequisites {
    <#
    .SYNOPSIS
        Removes Node.js (winget is a system component)
    #>
    param(
        [switch]$RemoveNodeJs
    )

    if ($RemoveNodeJs) {
        Write-SetupLog "Uninstalling Node.js..." "INFO"
        winget uninstall --id "OpenJS.NodeJS.LTS" --silent
        Write-SetupLog "Node.js uninstalled" "SUCCESS"
    }

    # Note: winget is a Windows component and should not be uninstalled
}
