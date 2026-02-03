#Requires -Version 5.1
<#
.SYNOPSIS
    Bootstrap script for remote installation of Windows development environment
.DESCRIPTION
    Downloads the windows-setup-scripts project from GitHub and runs the installer.
    Can be executed directly via: irm https://raw.githubusercontent.com/ushineko/ag-scripts/main/windows-setup-scripts/bootstrap.ps1 | iex
.EXAMPLE
    # Basic installation
    irm https://raw.githubusercontent.com/ushineko/ag-scripts/main/windows-setup-scripts/bootstrap.ps1 | iex

    # Dry run
    irm https://raw.githubusercontent.com/ushineko/ag-scripts/main/windows-setup-scripts/bootstrap.ps1 | iex; Install-DevEnv -DryRun

    # Install specific components
    irm https://raw.githubusercontent.com/ushineko/ag-scripts/main/windows-setup-scripts/bootstrap.ps1 | iex; Install-DevEnv -Components msys2,neovim
#>

$script:RepoUrl = "https://github.com/ushineko/ag-scripts/archive/refs/heads/main.zip"
$script:TempDir = "$env:TEMP\windows-setup-scripts-bootstrap"
$script:ExtractDir = "$script:TempDir\ag-scripts-main\windows-setup-scripts"

function Install-DevEnv {
    <#
    .SYNOPSIS
        Downloads and runs the Windows development environment installer
    .PARAMETER DryRun
        Show what would be installed without making changes
    .PARAMETER Components
        Specific components to install
    .PARAMETER Force
        Overwrite existing installations
    .PARAMETER KeepFiles
        Don't delete downloaded files after installation
    #>
    param(
        [switch]$DryRun,
        [string[]]$Components = @("all"),
        [switch]$Force,
        [switch]$KeepFiles
    )

    Write-Host ""
    Write-Host "  Windows Development Environment Bootstrap" -ForegroundColor Cyan
    Write-Host "  ==========================================" -ForegroundColor Cyan
    Write-Host ""

    try {
        # Clean up any previous bootstrap attempt
        if (Test-Path $script:TempDir) {
            Write-Host "  Cleaning up previous bootstrap files..." -ForegroundColor Yellow
            Remove-Item -Path $script:TempDir -Recurse -Force
        }

        # Create temp directory
        New-Item -ItemType Directory -Path $script:TempDir -Force | Out-Null

        # Download repo
        $zipPath = "$script:TempDir\repo.zip"
        Write-Host "  Downloading setup scripts from GitHub..." -ForegroundColor Cyan

        try {
            Invoke-WebRequest -Uri $script:RepoUrl -OutFile $zipPath -UseBasicParsing
        } catch {
            Write-Host "  Failed to download: $_" -ForegroundColor Red
            Write-Host ""
            Write-Host "  Troubleshooting:" -ForegroundColor Yellow
            Write-Host "  - Check your internet connection"
            Write-Host "  - Verify the repository URL is accessible"
            Write-Host "  - Try again later if GitHub is experiencing issues"
            return
        }

        if (-not (Test-Path $zipPath)) {
            Write-Host "  Download failed - file not created" -ForegroundColor Red
            return
        }

        # Extract
        Write-Host "  Extracting files..." -ForegroundColor Cyan
        Expand-Archive -Path $zipPath -DestinationPath $script:TempDir -Force

        # Verify extraction
        if (-not (Test-Path $script:ExtractDir)) {
            Write-Host "  Extraction failed - setup scripts not found" -ForegroundColor Red
            return
        }

        # Run installer
        $installerPath = "$script:ExtractDir\install.ps1"
        if (-not (Test-Path $installerPath)) {
            Write-Host "  Installer script not found: $installerPath" -ForegroundColor Red
            return
        }

        Write-Host "  Running installer..." -ForegroundColor Cyan
        Write-Host ""

        # Build arguments
        $args = @()
        if ($DryRun) { $args += "-DryRun" }
        if ($Force) { $args += "-Force" }
        if ($Components -and $Components -notcontains "all") {
            $args += "-Components"
            $args += ($Components -join ",")
        }

        # Execute installer
        & $installerPath @args

        # Cleanup (unless KeepFiles is specified)
        if (-not $KeepFiles) {
            Write-Host ""
            Write-Host "  Cleaning up temporary files..." -ForegroundColor Cyan
            Remove-Item -Path $script:TempDir -Recurse -Force -ErrorAction SilentlyContinue
        } else {
            Write-Host ""
            Write-Host "  Setup files kept at: $script:ExtractDir" -ForegroundColor Yellow
        }

    } catch {
        Write-Host "  Bootstrap failed: $_" -ForegroundColor Red
        Write-Host ""
        Write-Host "  Stack trace:" -ForegroundColor Yellow
        Write-Host $_.ScriptStackTrace
    }
}

# If script is executed directly (not dot-sourced), run installation
if ($MyInvocation.InvocationName -ne ".") {
    Install-DevEnv
}
