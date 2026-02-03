# ssh-agent.ps1 - Configure Windows OpenSSH Authentication Agent

. "$PSScriptRoot\..\lib\common.ps1"

$script:ServiceName = "ssh-agent"

function Test-SshAgent {
    <#
    .SYNOPSIS
        Tests if the Windows SSH Agent service is running
    #>
    try {
        $service = Get-Service -Name $script:ServiceName -ErrorAction SilentlyContinue
        return ($service -and $service.Status -eq "Running")
    } catch {
        return $false
    }
}

function Test-SshAgentInstalled {
    <#
    .SYNOPSIS
        Tests if Windows OpenSSH is installed (includes ssh-agent)
    #>
    $sshPath = "$env:SystemRoot\System32\OpenSSH\ssh.exe"
    return Test-Path $sshPath
}

function Install-SshAgent {
    <#
    .SYNOPSIS
        Configures and starts the Windows OpenSSH Authentication Agent service
    .DESCRIPTION
        The Windows ssh-agent service allows SSH keys to be loaded once and reused
        across sessions. This works with Git, ssh commands, and any tool using
        Windows OpenSSH (including from MSYS2 when using Windows ssh/ssh-add aliases).
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking Windows SSH Agent..." "INFO"

    # Check if OpenSSH is installed
    if (-not (Test-SshAgentInstalled)) {
        Write-SetupLog "Windows OpenSSH is not installed" "ERROR"
        Write-SetupLog "Please install OpenSSH via Settings > Apps > Optional Features > OpenSSH Client" "INFO"
        return $false
    }

    # Check current service status
    $service = Get-Service -Name $script:ServiceName -ErrorAction SilentlyContinue

    if (-not $service) {
        Write-SetupLog "SSH Agent service not found. OpenSSH may not be properly installed." "ERROR"
        return $false
    }

    $isRunning = $service.Status -eq "Running"
    $isAutoStart = $service.StartType -eq "Automatic"

    if ($isRunning -and $isAutoStart -and -not $Force) {
        Write-SetupLog "Windows SSH Agent is already configured and running" "SUCCESS"
        return $true
    }

    if ($DryRun) {
        Write-SetupLog "[DRY RUN] Would configure ssh-agent service to start automatically" "INFO"
        Write-SetupLog "[DRY RUN] Would start the ssh-agent service" "INFO"
        return $true
    }

    # Configure service to start automatically (requires admin)
    try {
        if (-not $isAutoStart) {
            Write-SetupLog "Setting ssh-agent service to start automatically..." "INFO"
            Set-Service -Name $script:ServiceName -StartupType Automatic
            Write-SetupLog "SSH Agent service set to Automatic startup" "SUCCESS"
        }
    } catch {
        Write-SetupLog "Failed to set service startup type (may need admin): $_" "WARNING"
        Write-SetupLog "You can run: Set-Service -Name ssh-agent -StartupType Automatic" "INFO"
    }

    # Start the service
    try {
        if (-not $isRunning) {
            Write-SetupLog "Starting ssh-agent service..." "INFO"
            Start-Service -Name $script:ServiceName
            Write-SetupLog "SSH Agent service started" "SUCCESS"
        }
    } catch {
        Write-SetupLog "Failed to start service (may need admin): $_" "WARNING"
        Write-SetupLog "You can run: Start-Service ssh-agent" "INFO"
    }

    # Verify final state
    $service = Get-Service -Name $script:ServiceName -ErrorAction SilentlyContinue
    if ($service.Status -eq "Running") {
        Write-SetupLog "Windows SSH Agent is now running" "SUCCESS"
        Write-SetupLog "Use 'ssh-add' to add your SSH keys" "INFO"
        return $true
    } else {
        Write-SetupLog "SSH Agent service is not running. Manual intervention may be required." "WARNING"
        return $true  # Don't fail the overall install
    }
}

function Uninstall-SshAgent {
    <#
    .SYNOPSIS
        Stops the SSH Agent service and sets it to manual startup
    .DESCRIPTION
        Does not remove OpenSSH itself - just reverts the service configuration
    #>
    Write-SetupLog "Reverting SSH Agent service configuration..." "INFO"

    $service = Get-Service -Name $script:ServiceName -ErrorAction SilentlyContinue

    if (-not $service) {
        Write-SetupLog "SSH Agent service not found" "INFO"
        return
    }

    try {
        if ($service.Status -eq "Running") {
            Stop-Service -Name $script:ServiceName -Force
            Write-SetupLog "SSH Agent service stopped" "INFO"
        }

        Set-Service -Name $script:ServiceName -StartupType Manual
        Write-SetupLog "SSH Agent service set to Manual startup" "SUCCESS"
    } catch {
        Write-SetupLog "Failed to configure service (may need admin): $_" "WARNING"
    }
}
