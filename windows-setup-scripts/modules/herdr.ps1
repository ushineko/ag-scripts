# herdr.ps1 - Install herdr terminal workspace manager

. "$PSScriptRoot\..\lib\common.ps1"

$script:HerdrConfigDir     = "$PSScriptRoot\..\configs\herdr"
$script:HerdrDestConfigDir = "$env:APPDATA\herdr"
$script:HerdrExePath       = "$env:LOCALAPPDATA\Programs\Herdr\bin\herdr.exe"
$script:HerdrInstallerUrl  = "https://herdr.dev/install.ps1"

function Test-Herdr {
    return Test-Installation -Path $script:HerdrExePath -ExpectedType "File"
}

function Install-Herdr {
    <#
    .SYNOPSIS
        Installs herdr via the official install.ps1 script and copies config

    .DESCRIPTION
        herdr is not distributed via winget (as of this writing). Its official
        Windows installer downloads a channel manifest from herdr.dev, verifies
        the SHA256 of the binary, and installs to
        $env:LOCALAPPDATA\Programs\Herdr\bin. The installer also touches
        $env:APPDATA\herdr\config.toml to record the selected update channel;
        this module copies the tracked config AFTER the installer runs so our
        version is authoritative.
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking herdr..." "INFO"

    if (-not (Test-Herdr) -or $Force) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would install herdr via $script:HerdrInstallerUrl" "INFO"
        } else {
            Write-SetupLog "Installing herdr via $script:HerdrInstallerUrl..." "INFO"
            try {
                Invoke-RestMethod $script:HerdrInstallerUrl | Invoke-Expression
            } catch {
                Write-SetupLog "herdr installer failed: $_" "ERROR"
                return $false
            }

            if (-not (Test-Herdr)) {
                Write-SetupLog "herdr installer ran but $script:HerdrExePath is missing" "ERROR"
                return $false
            }

            Refresh-EnvironmentPath
            Write-SetupLog "herdr installed successfully" "SUCCESS"
        }
    } else {
        Write-SetupLog "herdr is already installed" "SUCCESS"
    }

    # Copy config directory AFTER install so our config.toml wins over the
    # installer's channel-selection edit.
    if (Test-Path $script:HerdrConfigDir) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would copy herdr config to $script:HerdrDestConfigDir" "INFO"
        } else {
            Copy-ConfigDirectory -Source $script:HerdrConfigDir -Destination $script:HerdrDestConfigDir -Force:$Force | Out-Null
        }
    } else {
        Write-SetupLog "Config directory not found: $script:HerdrConfigDir" "WARNING"
    }

    Write-SetupLog "herdr setup complete" "SUCCESS"
    return $true
}

function Uninstall-Herdr {
    param(
        [switch]$RemoveConfig
    )

    Write-SetupLog "Uninstalling herdr..." "INFO"

    # The official installer does not ship a bundled uninstaller; the standalone
    # release is just an exe + release directory under $USERPROFILE\.herdr.
    $herdrInstallRoot = "$env:LOCALAPPDATA\Programs\Herdr"
    $herdrReleaseRoot = "$env:USERPROFILE\.herdr"

    foreach ($p in @($herdrInstallRoot, $herdrReleaseRoot)) {
        if (Test-Path $p) {
            Remove-Item -Path $p -Recurse -Force
            Write-SetupLog "Removed: $p" "SUCCESS"
        }
    }

    if ($RemoveConfig -and (Test-Path $script:HerdrDestConfigDir)) {
        Remove-Item -Path $script:HerdrDestConfigDir -Recurse -Force
        Write-SetupLog "Removed herdr config directory" "SUCCESS"
    }

    Write-SetupLog "herdr uninstalled" "SUCCESS"
}
