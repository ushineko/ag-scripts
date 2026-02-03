# powershell7.ps1 - Install PowerShell 7 (Core)

. "$PSScriptRoot\..\lib\common.ps1"

$script:Pwsh7Path = "$env:ProgramFiles\PowerShell\7\pwsh.exe"

function Test-PowerShell7 {
    return Test-Installation -Path $script:Pwsh7Path -ExpectedType "File"
}

function Install-PowerShell7 {
    <#
    .SYNOPSIS
        Installs PowerShell 7 via winget
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking PowerShell 7..." "INFO"

    if ((Test-PowerShell7) -and -not $Force) {
        $version = & $script:Pwsh7Path --version 2>$null
        Write-SetupLog "PowerShell 7 is already installed ($version)" "SUCCESS"
        return $true
    }

    if ($DryRun) {
        Write-SetupLog "[DRY RUN] Would install PowerShell 7 via winget" "INFO"
        return $true
    }

    $result = Install-WingetPackage -PackageId "Microsoft.PowerShell" -Name "PowerShell 7" -Force:$Force

    if ($result) {
        Refresh-EnvironmentPath
        Write-SetupLog "PowerShell 7 installed successfully" "SUCCESS"
    }

    return $result
}

function Uninstall-PowerShell7 {
    Write-SetupLog "Uninstalling PowerShell 7..." "INFO"
    Start-Process -FilePath "winget" -ArgumentList "uninstall --id Microsoft.PowerShell --silent --disable-interactivity" -Wait -WindowStyle Hidden
    Write-SetupLog "PowerShell 7 uninstalled" "SUCCESS"
}
