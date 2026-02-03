# claude-code.ps1 - Install Claude Code CLI

. "$PSScriptRoot\..\lib\common.ps1"

$script:ClaudePath = "$env:USERPROFILE\.local\bin\claude.exe"
$script:ConfigDir = "$PSScriptRoot\..\configs\claude"
$script:DestConfigDir = "$env:USERPROFILE\.claude"

function Test-ClaudeCode {
    # Check if claude is available in PATH or in the expected location
    try {
        $null = Get-Command claude -ErrorAction Stop
        return $true
    } catch {
        return Test-Installation -Path $script:ClaudePath -ExpectedType "File"
    }
}

function Install-ClaudeCode {
    <#
    .SYNOPSIS
        Installs Claude Code CLI via npm and copies CLAUDE.md
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking Claude Code..." "INFO"

    # Check for npm
    try {
        $null = Get-Command npm -ErrorAction Stop
    } catch {
        Write-SetupLog "npm is not available. Please install Node.js first." "ERROR"
        return $false
    }

    # Install Claude Code
    if (-not (Test-ClaudeCode) -or $Force) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would install Claude Code via npm" "INFO"
        } else {
            Write-SetupLog "Installing Claude Code via npm..." "INFO"

            try {
                $output = npm install -g @anthropic-ai/claude-code 2>&1
                Write-SetupLog "npm output: $output" "INFO"

                # Refresh PATH
                Refresh-EnvironmentPath

                if (Test-ClaudeCode) {
                    $version = claude --version 2>$null
                    Write-SetupLog "Claude Code installed successfully ($version)" "SUCCESS"
                } else {
                    Write-SetupLog "Claude Code installation may have succeeded but binary not found in PATH" "WARNING"
                }
            } catch {
                Write-SetupLog "Failed to install Claude Code: $_" "ERROR"
                return $false
            }
        }
    } else {
        $version = claude --version 2>$null
        Write-SetupLog "Claude Code is already installed ($version)" "SUCCESS"
    }

    # Copy CLAUDE.md
    $claudeMdSource = "$script:ConfigDir\CLAUDE.md"
    $claudeMdDest = "$script:DestConfigDir\CLAUDE.md"

    if (Test-Path $claudeMdSource) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would copy CLAUDE.md to $claudeMdDest" "INFO"
        } else {
            # Create .claude directory
            if (-not (Test-Path $script:DestConfigDir)) {
                New-Item -ItemType Directory -Path $script:DestConfigDir -Force | Out-Null
            }

            Copy-ConfigFile -Source $claudeMdSource -Destination $claudeMdDest -Force:$Force
        }
    }

    Write-SetupLog "Claude Code setup complete" "SUCCESS"
    return $true
}

function Uninstall-ClaudeCode {
    param(
        [switch]$RemoveConfig
    )

    Write-SetupLog "Uninstalling Claude Code..." "INFO"

    try {
        npm uninstall -g @anthropic-ai/claude-code 2>&1
        Write-SetupLog "Claude Code uninstalled" "SUCCESS"
    } catch {
        Write-SetupLog "Failed to uninstall Claude Code: $_" "WARNING"
    }

    if ($RemoveConfig -and (Test-Path $script:DestConfigDir)) {
        # Only remove CLAUDE.md, not credentials
        $claudeMd = "$script:DestConfigDir\CLAUDE.md"
        if (Test-Path $claudeMd) {
            Remove-Item -Path $claudeMd -Force
            Write-SetupLog "Removed CLAUDE.md" "SUCCESS"
        }

        # Warn about credentials
        Write-SetupLog "Note: Claude credentials in $script:DestConfigDir were preserved" "INFO"
    }
}
