# msys2.ps1 - Install MSYS2 and packages

. "$PSScriptRoot\..\lib\common.ps1"

$script:Msys2Path = "C:\msys64"
$script:ShellConfigDir = "$PSScriptRoot\..\configs\shell"
$script:Packages = @("git", "make", "vim", "zsh")

function Test-Msys2 {
    return Test-Installation -Path "$script:Msys2Path\usr\bin\bash.exe" -ExpectedType "File"
}

function Install-Msys2 {
    <#
    .SYNOPSIS
        Installs MSYS2 from GitHub releases, installs packages, and copies shell configs
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking MSYS2..." "INFO"

    # Install MSYS2
    if (-not (Test-Msys2) -or $Force) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would download and install MSYS2 from GitHub" "INFO"
        } else {
            $tempDir = "$env:TEMP\msys2-installer"
            $installerPath = "$tempDir\msys2-installer.exe"

            try {
                # Clean up previous temp files
                if (Test-Path $tempDir) {
                    Remove-Item -Path $tempDir -Recurse -Force
                }
                New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

                # Download installer
                $downloaded = Get-GitHubReleaseAsset -Repo "msys2/msys2-installer" -Pattern "msys2-x86_64-*.exe" -OutputPath $installerPath

                if (-not $downloaded) {
                    Write-SetupLog "Failed to download MSYS2 installer" "ERROR"
                    return $false
                }

                # Run silent install
                Write-SetupLog "Running MSYS2 installer (this may take a few minutes)..." "INFO"
                $process = Start-Process -FilePath $installerPath -ArgumentList "install", "--root", $script:Msys2Path, "--confirm-command" -Wait -PassThru -NoNewWindow

                if ($process.ExitCode -ne 0) {
                    Write-SetupLog "MSYS2 installer failed with exit code: $($process.ExitCode)" "ERROR"
                    return $false
                }

                # Cleanup installer
                Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue

                Write-SetupLog "MSYS2 installed successfully" "SUCCESS"

            } catch {
                Write-SetupLog "Failed to install MSYS2: $_" "ERROR"
                return $false
            }
        }
    } else {
        Write-SetupLog "MSYS2 is already installed at $script:Msys2Path" "SUCCESS"
    }

    # Update package database and install packages
    if (-not $DryRun) {
        Write-SetupLog "Updating MSYS2 package database..." "INFO"
        $bashExe = "$script:Msys2Path\usr\bin\bash.exe"

        # Update package database
        $updateResult = & $bashExe -l -c "pacman -Syu --noconfirm" 2>&1
        Write-SetupLog "Package database updated" "INFO"

        # Install packages
        $packagesStr = $script:Packages -join " "
        Write-SetupLog "Installing MSYS2 packages: $packagesStr" "INFO"
        & $bashExe -l -c "pacman -S --noconfirm --needed $packagesStr" 2>&1

        Write-SetupLog "MSYS2 packages installed" "SUCCESS"
    } else {
        Write-SetupLog "[DRY RUN] Would install packages: $($script:Packages -join ', ')" "INFO"
    }

    # Copy shell configs
    $configFiles = @(
        @{ Source = ".bashrc"; Dest = "$env:USERPROFILE\.bashrc" },
        @{ Source = ".zshrc"; Dest = "$env:USERPROFILE\.zshrc" },
        @{ Source = ".profile"; Dest = "$env:USERPROFILE\.profile" },
        @{ Source = ".bash-preexec.sh"; Dest = "$env:USERPROFILE\.bash-preexec.sh" }
    )

    foreach ($config in $configFiles) {
        $sourcePath = "$script:ShellConfigDir\$($config.Source)"
        if (Test-Path $sourcePath) {
            if ($DryRun) {
                Write-SetupLog "[DRY RUN] Would copy $($config.Source) to $($config.Dest)" "INFO"
            } else {
                Copy-ConfigFile -Source $sourcePath -Destination $config.Dest -Force:$Force
            }
        }
    }

    Write-SetupLog "MSYS2 setup complete" "SUCCESS"
    return $true
}

function Uninstall-Msys2 {
    param(
        [switch]$RemoveConfig
    )

    Write-SetupLog "Uninstalling MSYS2..." "INFO"

    if (Test-Path $script:Msys2Path) {
        # Run MSYS2 uninstaller if it exists
        $uninstaller = "$script:Msys2Path\uninstall.exe"
        if (Test-Path $uninstaller) {
            Start-Process -FilePath $uninstaller -ArgumentList "/S" -Wait -NoNewWindow
        } else {
            # Manual removal
            Remove-Item -Path $script:Msys2Path -Recurse -Force
        }
        Write-SetupLog "MSYS2 removed" "SUCCESS"
    }

    if ($RemoveConfig) {
        $configFiles = @(".bashrc", ".zshrc", ".profile", ".bash-preexec.sh")
        foreach ($file in $configFiles) {
            $path = "$env:USERPROFILE\$file"
            if (Test-Path $path) {
                Remove-Item -Path $path -Force
            }
        }
        Write-SetupLog "Shell config files removed" "SUCCESS"
    }
}
