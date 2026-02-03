# git.ps1 - Install Git for Windows

. "$PSScriptRoot\..\lib\common.ps1"

$script:GitPath = "$env:ProgramFiles\Git\cmd\git.exe"

function Test-GitForWindows {
    return Test-Installation -Path $script:GitPath -ExpectedType "File"
}

function Install-GitForWindows {
    <#
    .SYNOPSIS
        Installs Git for Windows via winget
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking Git for Windows..." "INFO"

    if ((Test-GitForWindows) -and -not $Force) {
        $version = & $script:GitPath --version 2>$null
        Write-SetupLog "Git for Windows is already installed ($version)" "SUCCESS"
        return $true
    }

    if ($DryRun) {
        Write-SetupLog "[DRY RUN] Would install Git for Windows via winget" "INFO"
        return $true
    }

    $result = Install-WingetPackage -PackageId "Git.Git" -Name "Git for Windows" -Force:$Force

    if ($result) {
        Refresh-EnvironmentPath
        Write-SetupLog "Git for Windows installed successfully" "SUCCESS"
    }

    return $result
}

function Uninstall-GitForWindows {
    Write-SetupLog "Uninstalling Git for Windows..." "INFO"
    winget uninstall --id "Git.Git" --silent --disable-interactivity
    Write-SetupLog "Git for Windows uninstalled" "SUCCESS"
}
