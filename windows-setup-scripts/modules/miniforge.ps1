# miniforge.ps1 - Install Miniforge3 (Conda distribution)

. "$PSScriptRoot\..\lib\common.ps1"

$script:MiniforgeDir = "C:\miniforge3"
$script:MiniforgeConfigDir = "$PSScriptRoot\..\configs\miniforge"

function Test-Miniforge {
    return Test-Installation -Path "$script:MiniforgeDir\Scripts\conda.exe" -ExpectedType "File"
}

function Install-Miniforge {
    <#
    .SYNOPSIS
        Installs Miniforge3 from GitHub releases and copies .condarc
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking Miniforge3..." "INFO"

    # Install Miniforge
    if (-not (Test-Miniforge) -or $Force) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would download and install Miniforge3 from GitHub" "INFO"
        } else {
            $tempDir = "$env:TEMP\miniforge-installer"
            $installerPath = "$tempDir\Miniforge3-installer.exe"

            try {
                # Clean up previous temp files
                if (Test-Path $tempDir) {
                    Remove-Item -Path $tempDir -Recurse -Force
                }
                New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

                # Download installer
                $downloaded = Get-GitHubReleaseAsset -Repo "conda-forge/miniforge" -Pattern "Miniforge3-Windows-x86_64.exe" -OutputPath $installerPath

                if (-not $downloaded) {
                    Write-SetupLog "Failed to download Miniforge3 installer" "ERROR"
                    return $false
                }

                # Run silent install
                Write-SetupLog "Running Miniforge3 installer (this may take a few minutes)..." "INFO"
                $args = "/S", "/InstallationType=JustMe", "/RegisterPython=0", "/AddToPath=0", "/D=$script:MiniforgeDir"
                $process = Start-Process -FilePath $installerPath -ArgumentList $args -Wait -PassThru -NoNewWindow

                if ($process.ExitCode -ne 0) {
                    Write-SetupLog "Miniforge3 installer failed with exit code: $($process.ExitCode)" "ERROR"
                    return $false
                }

                # Cleanup installer
                Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue

                # Add miniforge to system PATH
                $miniPaths = @(
                    $script:MiniforgeDir,
                    "$script:MiniforgeDir\Scripts",
                    "$script:MiniforgeDir\Library\bin"
                )

                $currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
                $pathsToAdd = @()

                foreach ($p in $miniPaths) {
                    if ($currentPath -notlike "*$p*") {
                        $pathsToAdd += $p
                    }
                }

                if ($pathsToAdd.Count -gt 0) {
                    $newPath = ($pathsToAdd -join ";") + ";" + $currentPath
                    try {
                        [Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
                        Write-SetupLog "Added Miniforge3 to system PATH" "SUCCESS"
                    } catch {
                        Write-SetupLog "Failed to update system PATH (may need admin): $_" "WARNING"
                        Write-SetupLog "You may need to manually add $script:MiniforgeDir to PATH" "INFO"
                    }
                }

                # Refresh PATH in current session
                Refresh-EnvironmentPath

                Write-SetupLog "Miniforge3 installed successfully" "SUCCESS"

            } catch {
                Write-SetupLog "Failed to install Miniforge3: $_" "ERROR"
                return $false
            }
        }
    } else {
        $condaExe = "$script:MiniforgeDir\Scripts\conda.exe"
        $version = & $condaExe --version 2>$null
        Write-SetupLog "Miniforge3 is already installed ($version)" "SUCCESS"
    }

    # Copy .condarc
    $condarcSource = "$script:MiniforgeConfigDir\.condarc"
    $condarcDest = "$script:MiniforgeDir\.condarc"

    if (Test-Path $condarcSource) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would copy .condarc to $condarcDest" "INFO"
        } else {
            Copy-ConfigFile -Source $condarcSource -Destination $condarcDest -Force:$Force
        }
    }

    Write-SetupLog "Miniforge3 setup complete" "SUCCESS"
    return $true
}

function Uninstall-Miniforge {
    param(
        [switch]$RemoveEnvs
    )

    Write-SetupLog "Uninstalling Miniforge3..." "INFO"

    if (Test-Path $script:MiniforgeDir) {
        # Run uninstaller if it exists
        $uninstaller = "$script:MiniforgeDir\Uninstall-Miniforge3.exe"
        if (Test-Path $uninstaller) {
            Start-Process -FilePath $uninstaller -ArgumentList "/S" -Wait -NoNewWindow
        } else {
            # Manual removal
            Remove-Item -Path $script:MiniforgeDir -Recurse -Force
        }
        Write-SetupLog "Miniforge3 removed" "SUCCESS"
    }

    # Remove conda config from user profile
    $userCondarc = "$env:USERPROFILE\.condarc"
    if (Test-Path $userCondarc) {
        Remove-Item -Path $userCondarc -Force
    }

    # Remove conda directory
    $condaDir = "$env:USERPROFILE\.conda"
    if ($RemoveEnvs -and (Test-Path $condaDir)) {
        Remove-Item -Path $condaDir -Recurse -Force
        Write-SetupLog "Removed .conda directory" "SUCCESS"
    }
}
