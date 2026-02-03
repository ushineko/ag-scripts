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
        Downloads and installs Antigravity from antigravity.google
    .DESCRIPTION
        Antigravity requires manual download following the link on the website.
        This function will attempt to automate the process or guide the user.
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
        Write-SetupLog "[DRY RUN] Would download Antigravity from antigravity.google" "INFO"
        return $true
    }

    # Antigravity requires following a download link on the website
    # We'll try to fetch the page and find the download link
    Write-SetupLog "Attempting to find Antigravity download link..." "INFO"

    try {
        # Fetch the landing page
        $response = Invoke-WebRequest -Uri "https://antigravity.google" -UseBasicParsing -MaximumRedirection 5

        # Look for download links in the page content
        $downloadLinks = $response.Links | Where-Object {
            $_.href -match "download|release|\.exe" -or
            $_.outerHTML -match "download"
        }

        if ($downloadLinks) {
            Write-SetupLog "Found potential download links. Attempting download..." "INFO"

            # Try to find a Windows installer link
            $installerLink = $downloadLinks | Where-Object {
                $_.href -match "windows|win|\.exe"
            } | Select-Object -First 1

            if ($installerLink) {
                $downloadUrl = $installerLink.href
                if (-not $downloadUrl.StartsWith("http")) {
                    $downloadUrl = "https://antigravity.google$downloadUrl"
                }

                $tempDir = "$env:TEMP\antigravity-installer"
                $installerPath = "$tempDir\antigravity-installer.exe"

                if (Test-Path $tempDir) {
                    Remove-Item -Path $tempDir -Recurse -Force
                }
                New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

                Write-SetupLog "Downloading from: $downloadUrl" "INFO"
                Invoke-WebRequest -Uri $downloadUrl -OutFile $installerPath -UseBasicParsing

                if (Test-Path $installerPath) {
                    Write-SetupLog "Running Antigravity installer..." "INFO"
                    Start-Process -FilePath $installerPath -Wait

                    Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue

                    if (Test-Antigravity) {
                        Write-SetupLog "Antigravity installed successfully" "SUCCESS"
                        return $true
                    }
                }
            }
        }

        # If automatic download failed, guide user
        Write-SetupLog "Automatic download not available. Please install manually:" "WARNING"
        Write-SetupLog "1. Visit https://antigravity.google" "INFO"
        Write-SetupLog "2. Click the download link" "INFO"
        Write-SetupLog "3. Run the installer" "INFO"
        Write-SetupLog "4. Re-run this script to continue" "INFO"

        return $false

    } catch {
        Write-SetupLog "Failed to download Antigravity: $_" "ERROR"
        Write-SetupLog "Please install manually from https://antigravity.google" "INFO"
        return $false
    }
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
