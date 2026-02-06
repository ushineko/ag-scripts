#Requires -Version 5.1
<#
.SYNOPSIS
    Windows Development Environment Setup Script
.DESCRIPTION
    Installs and configures a complete Windows development environment including:
    - PowerShell 7
    - Git for Windows
    - MSYS2 with zsh, git, make, vim
    - Oh My Posh (prompt engine)
    - Atuin (shell history)
    - Neovim with NvChad
    - Go
    - eza (modern ls replacement)
    - Miniforge3 (Conda)
    - Claude Code CLI
    - Antigravity
    - clockwork-orange
    - Windows Terminal profiles
    - Hack Nerd Font
.PARAMETER DryRun
    Show what would be installed without making changes
.PARAMETER Components
    Specific components to install (comma-separated).
    Options: prerequisites, powershell7, git, ssh-agent, fonts, msys2, oh-my-posh, atuin, neovim, golang, eza, miniforge, claude-code, antigravity, clockwork-orange, terminal, all
.PARAMETER Force
    Overwrite existing installations/configs
.PARAMETER SkipBackup
    Don't create backups (not recommended)
.EXAMPLE
    .\install.ps1
    Install all components
.EXAMPLE
    .\install.ps1 -DryRun
    Show what would be installed
.EXAMPLE
    .\install.ps1 -Components msys2,neovim
    Install only MSYS2 and Neovim
#>
param(
    [switch]$DryRun,
    [string[]]$Components = @("all"),
    [switch]$Force,
    [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"
$ScriptRoot = $PSScriptRoot

# Load library
. "$ScriptRoot\lib\common.ps1"

# Load modules
. "$ScriptRoot\modules\prerequisites.ps1"
. "$ScriptRoot\modules\powershell7.ps1"
. "$ScriptRoot\modules\git.ps1"
. "$ScriptRoot\modules\fonts.ps1"
. "$ScriptRoot\modules\msys2.ps1"
. "$ScriptRoot\modules\oh-my-posh.ps1"
. "$ScriptRoot\modules\atuin.ps1"
. "$ScriptRoot\modules\neovim.ps1"
. "$ScriptRoot\modules\golang.ps1"
. "$ScriptRoot\modules\miniforge.ps1"
. "$ScriptRoot\modules\claude-code.ps1"
. "$ScriptRoot\modules\antigravity.ps1"
. "$ScriptRoot\modules\clockwork-orange.ps1"
. "$ScriptRoot\modules\eza.ps1"
. "$ScriptRoot\modules\terminal.ps1"
. "$ScriptRoot\modules\ssh-agent.ps1"

function Show-Banner {
    Write-Host ""
    Write-Host "  Windows Development Environment Setup" -ForegroundColor Cyan
    Write-Host "  ======================================" -ForegroundColor Cyan
    Write-Host ""
}

function Main {
    Show-Banner

    # Initialize logging
    Initialize-SetupLog

    if ($DryRun) {
        Write-SetupLog "DRY RUN MODE - No changes will be made" "WARNING"
    }

    $installAll = $Components -contains "all"

    # Define installation order (dependencies first)
    $installOrder = @(
        @{ Name = "prerequisites"; Func = { Install-Prerequisites -DryRun:$DryRun -Force:$Force } }
        @{ Name = "powershell7";   Func = { Install-PowerShell7 -DryRun:$DryRun -Force:$Force } }
        @{ Name = "git";           Func = { Install-GitForWindows -DryRun:$DryRun -Force:$Force } }
        @{ Name = "ssh-agent";     Func = { Install-SshAgent -DryRun:$DryRun -Force:$Force } }
        @{ Name = "fonts";         Func = { Install-HackNerdFont -DryRun:$DryRun -Force:$Force } }
        @{ Name = "msys2";         Func = { Install-Msys2 -DryRun:$DryRun -Force:$Force } }
        @{ Name = "oh-my-posh";    Func = { Install-OhMyPosh -DryRun:$DryRun -Force:$Force } }
        @{ Name = "atuin";         Func = { Install-Atuin -DryRun:$DryRun -Force:$Force } }
        @{ Name = "golang";        Func = { Install-Go -DryRun:$DryRun -Force:$Force } }
        @{ Name = "eza";           Func = { Install-Eza -DryRun:$DryRun -Force:$Force } }
        @{ Name = "neovim";        Func = { Install-Neovim -DryRun:$DryRun -Force:$Force } }
        @{ Name = "miniforge";     Func = { Install-Miniforge -DryRun:$DryRun -Force:$Force } }
        @{ Name = "claude-code";   Func = { Install-ClaudeCode -DryRun:$DryRun -Force:$Force } }
        @{ Name = "antigravity";   Func = { Install-Antigravity -DryRun:$DryRun -Force:$Force } }
        @{ Name = "clockwork-orange"; Func = { Install-ClockworkOrange -DryRun:$DryRun -Force:$Force } }
        @{ Name = "terminal";      Func = { Install-TerminalProfiles -DryRun:$DryRun -Force:$Force } }
    )

    $failed = @()
    $succeeded = @()
    $skipped = @()

    foreach ($component in $installOrder) {
        if ($installAll -or $Components -contains $component.Name) {
            Write-Host ""
            Write-SetupLog "========== Installing: $($component.Name) ==========" "INFO"

            try {
                $result = & $component.Func

                if ($result) {
                    $succeeded += $component.Name
                } else {
                    $failed += $component.Name
                }
            } catch {
                Write-SetupLog "Error installing $($component.Name): $_" "ERROR"
                $failed += $component.Name

                if (-not $Force) {
                    Write-SetupLog "Stopping due to error. Use -Force to continue despite errors." "ERROR"
                    break
                }
            }
        } else {
            $skipped += $component.Name
        }
    }

    # Summary
    Write-Host ""
    Write-Host "  ======================================" -ForegroundColor Cyan
    Write-Host "  Installation Summary" -ForegroundColor Cyan
    Write-Host "  ======================================" -ForegroundColor Cyan
    Write-Host ""

    if ($succeeded.Count -gt 0) {
        Write-Host "  Succeeded: " -NoNewline -ForegroundColor Green
        Write-Host ($succeeded -join ", ")
    }

    if ($failed.Count -gt 0) {
        Write-Host "  Failed: " -NoNewline -ForegroundColor Red
        Write-Host ($failed -join ", ")
    }

    if ($skipped.Count -gt 0 -and -not $installAll) {
        Write-Host "  Skipped: " -NoNewline -ForegroundColor Yellow
        Write-Host ($skipped -join ", ")
    }

    Write-Host ""

    if ($failed.Count -eq 0) {
        Write-SetupLog "Installation complete!" "SUCCESS"
        Write-Host ""
        Write-Host "  Next steps:" -ForegroundColor Cyan
        Write-Host "  1. Restart your terminal to apply PATH changes"
        Write-Host "  2. Open Windows Terminal and select the MSYS2 profile"
        Write-Host "  3. Run 'nvim' to trigger plugin installation"
        Write-Host ""
        return 0
    } else {
        Write-SetupLog "Installation completed with errors" "WARNING"
        return 1
    }
}

exit (Main)
