# terminal.ps1 - Configure Windows Terminal profiles

. "$PSScriptRoot\..\lib\common.ps1"

$script:TerminalConfigDir = "$PSScriptRoot\..\configs\terminal"

function Get-WindowsTerminalSettingsPath {
    # Find Windows Terminal settings path
    $terminalPackages = Get-ChildItem -Path "$env:LOCALAPPDATA\Packages" -Filter "Microsoft.WindowsTerminal*" -Directory -ErrorAction SilentlyContinue

    foreach ($pkg in $terminalPackages) {
        $settingsPath = "$($pkg.FullName)\LocalState\settings.json"
        if (Test-Path $settingsPath) {
            return $settingsPath
        }
    }

    return $null
}

function Install-TerminalProfiles {
    <#
    .SYNOPSIS
        Merges custom profiles into Windows Terminal settings
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Configuring Windows Terminal..." "INFO"

    $settingsPath = Get-WindowsTerminalSettingsPath

    if (-not $settingsPath) {
        Write-SetupLog "Windows Terminal is not installed" "WARNING"
        Write-SetupLog "Install it from Microsoft Store: https://aka.ms/terminal" "INFO"
        return $false
    }

    Write-SetupLog "Found Windows Terminal settings at: $settingsPath" "INFO"

    $sourceProfilesPath = "$script:TerminalConfigDir\profiles.json"
    if (-not (Test-Path $sourceProfilesPath)) {
        Write-SetupLog "Source profiles not found: $sourceProfilesPath" "ERROR"
        return $false
    }

    if ($DryRun) {
        Write-SetupLog "[DRY RUN] Would merge custom profiles into Windows Terminal settings" "INFO"
        return $true
    }

    try {
        # Backup existing settings
        Backup-Item -Path $settingsPath | Out-Null

        # Read existing settings
        $existingSettings = Get-Content -Path $settingsPath -Raw | ConvertFrom-Json

        # Read our custom profiles
        $customSettings = Get-Content -Path $sourceProfilesPath -Raw | ConvertFrom-Json

        # Profiles to add/update
        $customProfiles = @(
            @{
                guid = "{7eb51a8e-fb55-4587-9d5d-a1d21d9887ae}"
                name = "MSYS2"
                commandline = "C:\msys64\usr\bin\zsh.exe -i -l"
                startingDirectory = "%USERPROFILE%"
                colorScheme = "One Half Dark"
                font = @{
                    face = "Hack Nerd Font Mono"
                    size = 10
                }
                hidden = $false
            },
            @{
                guid = "{c1a3d5e7-9b2f-4d6a-8e0c-1f2a3b4c5d6e}"
                name = "Claude Code"
                commandline = 'pwsh.exe -NoExit -Command "& claude"'
                startingDirectory = "%USERPROFILE%"
                colorScheme = "One Half Dark"
                icon = [char]::ConvertFromUtf32(0x1F916)  # Robot emoji
                font = @{
                    face = "Hack Nerd Font Mono"
                    size = 8
                }
                hidden = $false
            }
        )

        # Get existing profiles list
        $existingProfiles = $existingSettings.profiles.list

        foreach ($customProfile in $customProfiles) {
            # Check if profile already exists
            $existingProfile = $existingProfiles | Where-Object { $_.guid -eq $customProfile.guid }

            if ($existingProfile) {
                if ($Force) {
                    # Update existing profile
                    $index = [array]::IndexOf($existingProfiles, $existingProfile)
                    foreach ($key in $customProfile.Keys) {
                        $existingProfiles[$index].$key = $customProfile[$key]
                    }
                    Write-SetupLog "Updated profile: $($customProfile.name)" "INFO"
                } else {
                    Write-SetupLog "Profile exists (use -Force to update): $($customProfile.name)" "INFO"
                }
            } else {
                # Add new profile
                $newProfile = [PSCustomObject]$customProfile
                $existingProfiles += $newProfile
                Write-SetupLog "Added profile: $($customProfile.name)" "SUCCESS"
            }
        }

        # Update profiles list
        $existingSettings.profiles.list = $existingProfiles

        # Update default profile to PowerShell Core if not already set to one of our custom profiles
        $defaultProfile = $existingSettings.defaultProfile
        if (-not ($customProfiles.guid -contains $defaultProfile)) {
            # Find PowerShell Core profile
            $pwshProfile = $existingProfiles | Where-Object { $_.source -eq "Windows.Terminal.PowershellCore" }
            if ($pwshProfile) {
                $existingSettings.defaultProfile = $pwshProfile.guid
                Write-SetupLog "Set default profile to PowerShell Core" "INFO"
            }
        }

        # Write updated settings
        $existingSettings | ConvertTo-Json -Depth 10 | Set-Content -Path $settingsPath -Encoding UTF8

        Write-SetupLog "Windows Terminal profiles configured successfully" "SUCCESS"
        return $true

    } catch {
        Write-SetupLog "Failed to configure Windows Terminal: $_" "ERROR"
        return $false
    }
}

function Uninstall-TerminalProfiles {
    <#
    .SYNOPSIS
        Removes custom profiles from Windows Terminal settings
    #>
    param(
        [switch]$RemoveAll
    )

    Write-SetupLog "Removing custom Windows Terminal profiles..." "INFO"

    $settingsPath = Get-WindowsTerminalSettingsPath
    if (-not $settingsPath) {
        Write-SetupLog "Windows Terminal settings not found" "INFO"
        return
    }

    try {
        $settings = Get-Content -Path $settingsPath -Raw | ConvertFrom-Json

        # GUIDs of our custom profiles
        $customGuids = @(
            "{7eb51a8e-fb55-4587-9d5d-a1d21d9887ae}",  # MSYS2
            "{c1a3d5e7-9b2f-4d6a-8e0c-1f2a3b4c5d6e}"   # Claude Code
        )

        # Filter out our custom profiles
        $settings.profiles.list = $settings.profiles.list | Where-Object { $_.guid -notin $customGuids }

        # Write updated settings
        $settings | ConvertTo-Json -Depth 10 | Set-Content -Path $settingsPath -Encoding UTF8

        Write-SetupLog "Custom profiles removed from Windows Terminal" "SUCCESS"

    } catch {
        Write-SetupLog "Failed to remove profiles: $_" "ERROR"
    }
}
