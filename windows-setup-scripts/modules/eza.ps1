# eza.ps1 - Install eza (modern replacement for ls)

. "$PSScriptRoot\..\lib\common.ps1"

$script:EzaPath = "$env:LOCALAPPDATA\Microsoft\WinGet\Links\eza.exe"

function Test-Eza {
    return Test-Installation -Path $script:EzaPath -ExpectedType "File"
}

function Install-Eza {
    <#
    .SYNOPSIS
        Installs eza via winget
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking eza..." "INFO"

    if ((Test-Eza) -and -not $Force) {
        $version = & eza --version 2>$null | Select-Object -First 1
        Write-SetupLog "eza is already installed ($version)" "SUCCESS"
        return $true
    }

    if ($DryRun) {
        Write-SetupLog "[DRY RUN] Would install eza via winget" "INFO"
        return $true
    }

    $result = Install-WingetPackage -PackageId "eza-community.eza" -Name "eza" -Force:$Force

    if ($result) {
        Refresh-EnvironmentPath
        Write-SetupLog "eza installed successfully" "SUCCESS"
    }

    return $result
}

function Uninstall-Eza {
    Write-SetupLog "Uninstalling eza..." "INFO"
    Start-Process -FilePath "winget" -ArgumentList "uninstall --id eza-community.eza --silent --disable-interactivity" -Wait -WindowStyle Hidden
    Write-SetupLog "eza uninstalled" "SUCCESS"
}
