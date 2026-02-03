# common.ps1 - Shared utility functions for Windows Setup Scripts
# Provides logging, backup, file operations, and download utilities

$script:LogFile = $null

function Initialize-SetupLog {
    param(
        [string]$LogPath = "$env:TEMP\windows-setup-scripts.log"
    )
    $script:LogFile = $LogPath
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $script:LogFile -Value "`n`n========== Setup Started: $timestamp =========="
}

function Write-SetupLog {
    param(
        [Parameter(Mandatory)]
        [string]$Message,
        [ValidateSet("INFO", "SUCCESS", "WARNING", "ERROR")]
        [string]$Level = "INFO"
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"

    # Console output with colors
    $color = switch ($Level) {
        "INFO"    { "Cyan" }
        "SUCCESS" { "Green" }
        "WARNING" { "Yellow" }
        "ERROR"   { "Red" }
    }
    Write-Host $logMessage -ForegroundColor $color

    # File output
    if ($script:LogFile) {
        Add-Content -Path $script:LogFile -Value $logMessage
    }
}

function Backup-Item {
    <#
    .SYNOPSIS
        Creates a timestamped backup of a file or directory
    .DESCRIPTION
        If the target exists, creates a backup with format: original.backup.yyyyMMdd_HHmmss
    .RETURNS
        The backup path if created, $null otherwise
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    if (Test-Path $Path) {
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $backupPath = "$Path.backup.$timestamp"

        try {
            Copy-Item -Path $Path -Destination $backupPath -Recurse -Force
            Write-SetupLog "Backed up: $Path -> $backupPath" "INFO"
            return $backupPath
        } catch {
            Write-SetupLog "Failed to backup $Path : $_" "ERROR"
            return $null
        }
    }
    return $null
}

function Copy-ConfigFile {
    <#
    .SYNOPSIS
        Copies a config file with backup support
    .DESCRIPTION
        Creates parent directories if needed, backs up existing files, then copies
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Source,
        [Parameter(Mandatory)]
        [string]$Destination,
        [switch]$Force,
        [switch]$SkipBackup
    )

    # Verify source exists
    if (-not (Test-Path $Source)) {
        Write-SetupLog "Source file not found: $Source" "ERROR"
        return $false
    }

    # Check if destination exists
    if (Test-Path $Destination) {
        if (-not $Force) {
            Write-SetupLog "File exists (use -Force to overwrite): $Destination" "WARNING"
            return $false
        }
        if (-not $SkipBackup) {
            Backup-Item -Path $Destination | Out-Null
        }
    }

    # Create parent directory if needed
    $destDir = Split-Path -Parent $Destination
    if ($destDir -and -not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        Write-SetupLog "Created directory: $destDir" "INFO"
    }

    # Copy file
    try {
        Copy-Item -Path $Source -Destination $Destination -Force
        Write-SetupLog "Copied: $Source -> $Destination" "SUCCESS"
        return $true
    } catch {
        Write-SetupLog "Failed to copy $Source : $_" "ERROR"
        return $false
    }
}

function Copy-ConfigDirectory {
    <#
    .SYNOPSIS
        Recursively copies a config directory with backup support
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Source,
        [Parameter(Mandatory)]
        [string]$Destination,
        [switch]$Force,
        [switch]$SkipBackup
    )

    if (-not (Test-Path $Source)) {
        Write-SetupLog "Source directory not found: $Source" "ERROR"
        return $false
    }

    if (Test-Path $Destination) {
        if (-not $Force) {
            Write-SetupLog "Directory exists (use -Force to overwrite): $Destination" "WARNING"
            return $false
        }
        if (-not $SkipBackup) {
            Backup-Item -Path $Destination | Out-Null
        }
        Remove-Item -Path $Destination -Recurse -Force
    }

    try {
        Copy-Item -Path $Source -Destination $Destination -Recurse -Force
        Write-SetupLog "Copied directory: $Source -> $Destination" "SUCCESS"
        return $true
    } catch {
        Write-SetupLog "Failed to copy directory $Source : $_" "ERROR"
        return $false
    }
}

function Test-Installation {
    <#
    .SYNOPSIS
        Tests if a component is installed at expected location
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [ValidateSet("File", "Directory", "Any")]
        [string]$ExpectedType = "Any"
    )

    if (-not (Test-Path $Path)) {
        return $false
    }

    $item = Get-Item $Path
    switch ($ExpectedType) {
        "File"      { return -not $item.PSIsContainer }
        "Directory" { return $item.PSIsContainer }
        default     { return $true }
    }
}

function Test-WingetPackage {
    <#
    .SYNOPSIS
        Checks if a package is installed via winget
    #>
    param(
        [Parameter(Mandatory)]
        [string]$PackageId
    )

    try {
        $result = winget list --id $PackageId 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Install-WingetPackage {
    <#
    .SYNOPSIS
        Installs a package via winget with idempotency
    #>
    param(
        [Parameter(Mandatory)]
        [string]$PackageId,
        [string]$Name = $PackageId,
        [switch]$Force
    )

    if ((Test-WingetPackage -PackageId $PackageId) -and -not $Force) {
        Write-SetupLog "$Name is already installed" "SUCCESS"
        return $true
    }

    Write-SetupLog "Installing $Name via winget..." "INFO"

    try {
        # Use Start-Process to avoid output buffering issues when run via irm | iex
        $wingetArgs = "install --id $PackageId --exact --silent --accept-package-agreements --accept-source-agreements --disable-interactivity"
        $process = Start-Process -FilePath "winget" -ArgumentList $wingetArgs -Wait -PassThru -NoNewWindow

        if ($process.ExitCode -eq 0) {
            Write-SetupLog "$Name installed successfully" "SUCCESS"
            return $true
        } else {
            Write-SetupLog "Failed to install $Name (exit code: $($process.ExitCode))" "ERROR"
            return $false
        }
    } catch {
        Write-SetupLog "Exception installing $Name : $_" "ERROR"
        return $false
    }
}

function Get-GitHubReleaseAsset {
    <#
    .SYNOPSIS
        Downloads an asset from the latest GitHub release
    .DESCRIPTION
        Uses GitHub API to find the latest release and download matching asset
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Repo,  # Format: "owner/repo"
        [Parameter(Mandatory)]
        [string]$Pattern,  # Glob pattern to match asset name
        [Parameter(Mandatory)]
        [string]$OutputPath
    )

    $apiUrl = "https://api.github.com/repos/$Repo/releases/latest"

    try {
        Write-SetupLog "Fetching latest release from $Repo..." "INFO"
        $release = Invoke-RestMethod -Uri $apiUrl -Headers @{ "User-Agent" = "Windows-Setup-Scripts" }

        # Find matching asset
        $asset = $release.assets | Where-Object { $_.name -like $Pattern } | Select-Object -First 1

        if (-not $asset) {
            Write-SetupLog "No asset matching pattern '$Pattern' found in release" "ERROR"
            return $null
        }

        $downloadUrl = $asset.browser_download_url
        $fileName = $asset.name

        Write-SetupLog "Downloading $fileName..." "INFO"
        Invoke-WebRequest -Uri $downloadUrl -OutFile $OutputPath -UseBasicParsing

        if (Test-Path $OutputPath) {
            Write-SetupLog "Downloaded: $OutputPath" "SUCCESS"
            return $OutputPath
        } else {
            Write-SetupLog "Download failed - file not found" "ERROR"
            return $null
        }
    } catch {
        Write-SetupLog "Failed to download from GitHub: $_" "ERROR"
        return $null
    }
}

function Test-DownloadUrl {
    <#
    .SYNOPSIS
        Tests if a URL is reachable
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -Method Head -UseBasicParsing -TimeoutSec 10
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-DownloadUrls {
    <#
    .SYNOPSIS
        Loads download URLs from the config file
    #>
    param(
        [string]$ConfigPath = "$PSScriptRoot\..\configs\download-urls.json"
    )

    if (-not (Test-Path $ConfigPath)) {
        Write-SetupLog "Download URLs config not found: $ConfigPath" "ERROR"
        return $null
    }

    try {
        $content = Get-Content -Path $ConfigPath -Raw
        return $content | ConvertFrom-Json
    } catch {
        Write-SetupLog "Failed to parse download URLs config: $_" "ERROR"
        return $null
    }
}

function Invoke-WithRetry {
    <#
    .SYNOPSIS
        Executes a script block with retry logic
    #>
    param(
        [Parameter(Mandatory)]
        [scriptblock]$ScriptBlock,
        [int]$MaxRetries = 3,
        [int]$DelaySeconds = 5
    )

    $attempt = 0
    while ($attempt -lt $MaxRetries) {
        $attempt++
        try {
            return & $ScriptBlock
        } catch {
            if ($attempt -eq $MaxRetries) {
                throw
            }
            Write-SetupLog "Attempt $attempt failed, retrying in $DelaySeconds seconds..." "WARNING"
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

function Refresh-EnvironmentPath {
    <#
    .SYNOPSIS
        Refreshes the PATH environment variable in the current session
    #>
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Write-SetupLog "Refreshed PATH environment variable" "INFO"
}

# Note: Functions are automatically available when dot-sourced
