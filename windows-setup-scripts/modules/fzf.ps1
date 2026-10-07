# fzf.ps1 - Install fzf fuzzy finder
#
# Used by the herdr project tab picker (configs\herdr\scripts\herdr-project-tab.ps1,
# prefix+shift+c). No config to copy.

. "$PSScriptRoot\..\lib\common.ps1"

function Test-Fzf {
    try {
        $null = Get-Command fzf -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Install-Fzf {
    <#
    .SYNOPSIS
        Installs fzf via winget
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking fzf..." "INFO"

    if (-not (Test-Fzf) -or $Force) {
        if ($DryRun) {
            Write-SetupLog "[DRY RUN] Would install fzf via winget" "INFO"
        } else {
            $result = Install-WingetPackage -PackageId "junegunn.fzf" -Name "fzf" -Force:$Force

            if (-not $result) {
                Write-SetupLog "Failed to install fzf" "ERROR"
                return $false
            }

            Refresh-EnvironmentPath
        }
    } else {
        $version = & fzf --version 2>$null | Select-Object -First 1
        Write-SetupLog "fzf is already installed ($version)" "SUCCESS"
    }

    Write-SetupLog "fzf setup complete" "SUCCESS"
    return $true
}

function Uninstall-Fzf {
    Write-SetupLog "Uninstalling fzf..." "INFO"
    Start-Process -FilePath "winget" -ArgumentList "uninstall --id junegunn.fzf --silent --disable-interactivity" -Wait -WindowStyle Hidden
    Write-SetupLog "fzf uninstalled" "SUCCESS"
}
