#Requires -Version 5.1
<#
.SYNOPSIS
    Tests that all components are installed correctly
.DESCRIPTION
    Verifies that each component is properly installed and functional.
    Run after installation to validate the setup.
.EXAMPLE
    .\tests\test-installation.ps1
#>

$ScriptRoot = Split-Path -Parent $PSScriptRoot

function Test-Command {
    param(
        [string]$Command,
        [string]$Args = "--version"
    )

    try {
        $output = & $Command $Args 2>&1
        return @{
            Success = $true
            Output = ($output | Select-Object -First 1)
        }
    } catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
        }
    }
}

function Test-Path-Exists {
    param(
        [string]$Path,
        [string]$Type = "Any"
    )

    if (Test-Path $Path) {
        $item = Get-Item $Path
        $isCorrectType = switch ($Type) {
            "File" { -not $item.PSIsContainer }
            "Directory" { $item.PSIsContainer }
            default { $true }
        }
        return @{
            Success = $isCorrectType
            Exists = $true
        }
    }
    return @{
        Success = $false
        Exists = $false
    }
}

function Main {
    Write-Host ""
    Write-Host "  Installation Verification" -ForegroundColor Cyan
    Write-Host "  =========================" -ForegroundColor Cyan
    Write-Host ""

    $tests = @(
        @{
            Name = "PowerShell 7"
            Test = { Test-Command -Command "pwsh" }
        },
        @{
            Name = "Git for Windows"
            Test = { Test-Command -Command "git" }
        },
        @{
            Name = "MSYS2"
            Test = { Test-Path-Exists -Path "C:\msys64\usr\bin\bash.exe" -Type "File" }
        },
        @{
            Name = "MSYS2 Zsh"
            Test = { Test-Path-Exists -Path "C:\msys64\usr\bin\zsh.exe" -Type "File" }
        },
        @{
            Name = "Oh My Posh"
            Test = { Test-Command -Command "oh-my-posh" }
        },
        @{
            Name = "Atuin"
            Test = { Test-Command -Command "atuin" }
        },
        @{
            Name = "Go"
            Test = { Test-Command -Command "go" -Args "version" }
        },
        @{
            Name = "Neovim"
            Test = { Test-Command -Command "nvim" }
        },
        @{
            Name = "NvChad Config"
            Test = { Test-Path-Exists -Path "$env:LOCALAPPDATA\nvim\init.lua" -Type "File" }
        },
        @{
            Name = "Miniforge3"
            Test = { Test-Path-Exists -Path "C:\miniforge3\Scripts\conda.exe" -Type "File" }
        },
        @{
            Name = "Claude Code"
            Test = { Test-Command -Command "claude" }
        },
        @{
            Name = "Antigravity"
            Test = { Test-Command -Command "antigravity" }
        },
        @{
            Name = "clockwork-orange"
            Test = { Test-Path-Exists -Path "$env:LOCALAPPDATA\Programs\clockwork-orange" -Type "Directory" }
        },
        @{
            Name = "Hack Nerd Font"
            Test = {
                $userFonts = "$env:LOCALAPPDATA\Microsoft\Windows\Fonts"
                $hackFonts = Get-ChildItem -Path $userFonts -Filter "*Hack*" -ErrorAction SilentlyContinue
                @{
                    Success = $hackFonts.Count -gt 0
                    Output = "$($hackFonts.Count) font files"
                }
            }
        },
        @{
            Name = "Shell Config (.bashrc)"
            Test = { Test-Path-Exists -Path "$env:USERPROFILE\.bashrc" -Type "File" }
        },
        @{
            Name = "Shell Config (.zshrc)"
            Test = { Test-Path-Exists -Path "$env:USERPROFILE\.zshrc" -Type "File" }
        },
        @{
            Name = "Oh My Posh Theme"
            Test = { Test-Path-Exists -Path "$env:USERPROFILE\.config\oh-my-posh\powerlevel10k_rainbow.omp.json" -Type "File" }
        },
        @{
            Name = "Atuin Config"
            Test = { Test-Path-Exists -Path "$env:USERPROFILE\.config\atuin\config.toml" -Type "File" }
        }
    )

    $passed = 0
    $failed = 0

    foreach ($test in $tests) {
        Write-Host "  $($test.Name): " -NoNewline

        $result = & $test.Test

        if ($result.Success) {
            Write-Host "PASS" -ForegroundColor Green -NoNewline
            if ($result.Output) {
                Write-Host " ($($result.Output))"
            } else {
                Write-Host ""
            }
            $passed++
        } else {
            Write-Host "FAIL" -ForegroundColor Red
            if ($result.Error) {
                Write-Host "    Error: $($result.Error)" -ForegroundColor Yellow
            }
            $failed++
        }
    }

    Write-Host ""
    Write-Host "  =========================" -ForegroundColor Cyan
    Write-Host "  Passed: $passed" -ForegroundColor Green
    Write-Host "  Failed: $failed" -ForegroundColor $(if ($failed -gt 0) { "Red" } else { "Green" })
    Write-Host ""

    if ($failed -eq 0) {
        Write-Host "  All tests passed!" -ForegroundColor Green
        return 0
    } else {
        Write-Host "  Some tests failed. Run install.ps1 to fix missing components." -ForegroundColor Yellow
        return 1
    }
}

exit (Main)
