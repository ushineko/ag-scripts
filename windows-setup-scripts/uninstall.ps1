#Requires -Version 5.1
<#
.SYNOPSIS
    Windows Development Environment Uninstaller
.DESCRIPTION
    Removes components installed by the setup scripts.
    By default, preserves configuration files and user data.
.PARAMETER RemoveConfigs
    Also remove configuration files (backups will be preserved)
.PARAMETER Components
    Specific components to uninstall (comma-separated).
    Options: powershell7, git, ssh-agent, fonts, msys2, oh-my-posh, atuin, neovim, golang, eza, miniforge, claude-code, antigravity, clockwork-orange, terminal, all
.PARAMETER Force
    Skip confirmation prompts
.EXAMPLE
    .\uninstall.ps1
    Uninstall all components, preserve configs
.EXAMPLE
    .\uninstall.ps1 -RemoveConfigs
    Uninstall all components and remove configs
.EXAMPLE
    .\uninstall.ps1 -Components msys2,neovim
    Uninstall only MSYS2 and Neovim
#>
param(
    [switch]$RemoveConfigs,
    [string[]]$Components = @("all"),
    [switch]$Force
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
    Write-Host "  Windows Development Environment Uninstaller" -ForegroundColor Yellow
    Write-Host "  ============================================" -ForegroundColor Yellow
    Write-Host ""
}

function Main {
    Show-Banner

    # Initialize logging
    Initialize-SetupLog -LogPath "$env:TEMP\windows-setup-uninstall.log"

    $uninstallAll = $Components -contains "all"

    # Show warning
    if (-not $Force) {
        Write-Host "  This will uninstall the following components:" -ForegroundColor Yellow
        Write-Host ""

        $uninstallOrder = @(
            "terminal", "clockwork-orange", "antigravity", "claude-code",
            "miniforge", "neovim", "eza", "golang", "atuin", "oh-my-posh",
            "msys2", "fonts", "ssh-agent", "git", "powershell7"
        )

        foreach ($comp in $uninstallOrder) {
            if ($uninstallAll -or $Components -contains $comp) {
                Write-Host "    - $comp" -ForegroundColor Cyan
            }
        }

        if ($RemoveConfigs) {
            Write-Host ""
            Write-Host "  Configuration files WILL be removed." -ForegroundColor Red
        } else {
            Write-Host ""
            Write-Host "  Configuration files will be preserved." -ForegroundColor Green
        }

        Write-Host ""
        $confirm = Read-Host "  Continue? (y/N)"
        if ($confirm -ne "y" -and $confirm -ne "Y") {
            Write-Host "  Cancelled." -ForegroundColor Yellow
            return 0
        }
    }

    # Define uninstallation order (reverse of installation)
    $uninstallOrder = @(
        @{ Name = "terminal";        Func = { Uninstall-TerminalProfiles -RemoveAll:$RemoveConfigs } }
        @{ Name = "clockwork-orange"; Func = { Uninstall-ClockworkOrange } }
        @{ Name = "antigravity";     Func = { Uninstall-Antigravity } }
        @{ Name = "claude-code";     Func = { Uninstall-ClaudeCode -RemoveConfig:$RemoveConfigs } }
        @{ Name = "miniforge";       Func = { Uninstall-Miniforge -RemoveEnvs:$RemoveConfigs } }
        @{ Name = "neovim";          Func = { Uninstall-Neovim -RemoveConfig:$RemoveConfigs } }
        @{ Name = "eza";             Func = { Uninstall-Eza } }
        @{ Name = "golang";          Func = { Uninstall-Go } }
        @{ Name = "atuin";           Func = { Uninstall-Atuin -RemoveConfig:$RemoveConfigs } }
        @{ Name = "oh-my-posh";      Func = { Uninstall-OhMyPosh -RemoveConfig:$RemoveConfigs } }
        @{ Name = "msys2";           Func = { Uninstall-Msys2 -RemoveConfig:$RemoveConfigs } }
        @{ Name = "fonts";           Func = { Uninstall-HackNerdFont } }
        @{ Name = "ssh-agent";       Func = { Uninstall-SshAgent } }
        @{ Name = "git";             Func = { Uninstall-GitForWindows } }
        @{ Name = "powershell7";     Func = { Uninstall-PowerShell7 } }
    )

    foreach ($component in $uninstallOrder) {
        if ($uninstallAll -or $Components -contains $component.Name) {
            Write-Host ""
            Write-SetupLog "========== Uninstalling: $($component.Name) ==========" "INFO"

            try {
                & $component.Func
            } catch {
                Write-SetupLog "Error uninstalling $($component.Name): $_" "ERROR"
            }
        }
    }

    Write-Host ""
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-SetupLog "Uninstallation complete" "SUCCESS"
    Write-Host ""
    Write-Host "  Note: Node.js and winget were not uninstalled (system prerequisites)" -ForegroundColor Yellow
    Write-Host "  Note: Backup files (.backup.*) were preserved in their original locations" -ForegroundColor Yellow
    Write-Host ""

    return 0
}

exit (Main)
