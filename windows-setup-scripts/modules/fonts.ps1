# fonts.ps1 - Install Hack Nerd Font

. "$PSScriptRoot\..\lib\common.ps1"

$script:FontName = "Hack Nerd Font Mono"
$script:FontRegistryPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"

function Test-HackNerdFont {
    # Check if font is registered in Windows
    try {
        $fonts = Get-ItemProperty -Path $script:FontRegistryPath -ErrorAction SilentlyContinue
        foreach ($prop in $fonts.PSObject.Properties) {
            if ($prop.Name -like "*Hack*Nerd*") {
                return $true
            }
        }
    } catch {
        # Fallback: check user fonts folder
        $userFonts = "$env:LOCALAPPDATA\Microsoft\Windows\Fonts"
        return (Get-ChildItem -Path $userFonts -Filter "*Hack*Nerd*" -ErrorAction SilentlyContinue).Count -gt 0
    }
    return $false
}

function Install-HackNerdFont {
    <#
    .SYNOPSIS
        Downloads and installs Hack Nerd Font from GitHub releases
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking Hack Nerd Font..." "INFO"

    if ((Test-HackNerdFont) -and -not $Force) {
        Write-SetupLog "Hack Nerd Font is already installed" "SUCCESS"
        return $true
    }

    if ($DryRun) {
        Write-SetupLog "[DRY RUN] Would download and install Hack Nerd Font from GitHub" "INFO"
        return $true
    }

    # Download from GitHub releases
    $tempDir = "$env:TEMP\hack-nerd-font"
    $zipPath = "$tempDir\Hack.zip"

    try {
        # Clean up any previous temp files
        if (Test-Path $tempDir) {
            Remove-Item -Path $tempDir -Recurse -Force
        }
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

        # Download
        $downloaded = Get-GitHubReleaseAsset -Repo "ryanoasis/nerd-fonts" -Pattern "Hack.zip" -OutputPath $zipPath

        if (-not $downloaded) {
            Write-SetupLog "Failed to download Hack Nerd Font" "ERROR"
            return $false
        }

        # Extract
        Write-SetupLog "Extracting font files..." "INFO"
        Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

        # Install fonts to user fonts directory
        $userFontsDir = "$env:LOCALAPPDATA\Microsoft\Windows\Fonts"
        if (-not (Test-Path $userFontsDir)) {
            New-Item -ItemType Directory -Path $userFontsDir -Force | Out-Null
        }

        # Copy font files
        $fontFiles = Get-ChildItem -Path $tempDir -Filter "*.ttf" -Recurse
        $installed = 0

        foreach ($font in $fontFiles) {
            # Skip Windows Compatible versions if regular exists
            if ($font.Name -match "Windows Compatible") {
                continue
            }

            $destPath = Join-Path $userFontsDir $font.Name
            Copy-Item -Path $font.FullName -Destination $destPath -Force

            # Register font in user registry
            $fontRegPath = "HKCU:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
            $fontName = [System.IO.Path]::GetFileNameWithoutExtension($font.Name) + " (TrueType)"
            Set-ItemProperty -Path $fontRegPath -Name $fontName -Value $destPath -ErrorAction SilentlyContinue

            $installed++
        }

        Write-SetupLog "Installed $installed font files" "SUCCESS"

        # Cleanup
        Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue

        Write-SetupLog "Hack Nerd Font installed successfully" "SUCCESS"
        Write-SetupLog "Note: You may need to restart applications to see the new font" "INFO"
        return $true

    } catch {
        Write-SetupLog "Failed to install Hack Nerd Font: $_" "ERROR"
        return $false
    }
}

function Uninstall-HackNerdFont {
    Write-SetupLog "Uninstalling Hack Nerd Font..." "INFO"

    $userFontsDir = "$env:LOCALAPPDATA\Microsoft\Windows\Fonts"
    $fontFiles = Get-ChildItem -Path $userFontsDir -Filter "*Hack*" -ErrorAction SilentlyContinue

    foreach ($font in $fontFiles) {
        Remove-Item -Path $font.FullName -Force -ErrorAction SilentlyContinue

        # Remove registry entry
        $fontRegPath = "HKCU:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
        $fontName = [System.IO.Path]::GetFileNameWithoutExtension($font.Name) + " (TrueType)"
        Remove-ItemProperty -Path $fontRegPath -Name $fontName -ErrorAction SilentlyContinue
    }

    Write-SetupLog "Hack Nerd Font uninstalled" "SUCCESS"
}
