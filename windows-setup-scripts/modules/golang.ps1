# golang.ps1 - Install Go programming language

. "$PSScriptRoot\..\lib\common.ps1"

$script:GoPath = "C:\Go\bin\go.exe"

function Test-Go {
    return Test-Installation -Path $script:GoPath -ExpectedType "File"
}

function Install-Go {
    <#
    .SYNOPSIS
        Installs Go via winget
    #>
    param(
        [switch]$DryRun,
        [switch]$Force
    )

    Write-SetupLog "Checking Go..." "INFO"

    if ((Test-Go) -and -not $Force) {
        $version = & $script:GoPath version 2>$null
        Write-SetupLog "Go is already installed ($version)" "SUCCESS"
        return $true
    }

    if ($DryRun) {
        Write-SetupLog "[DRY RUN] Would install Go via winget" "INFO"
        return $true
    }

    $result = Install-WingetPackage -PackageId "GoLang.Go" -Name "Go" -Force:$Force

    if ($result) {
        Refresh-EnvironmentPath
        Write-SetupLog "Go installed successfully" "SUCCESS"
    }

    return $result
}

function Uninstall-Go {
    Write-SetupLog "Uninstalling Go..." "INFO"
    winget uninstall --id "GoLang.Go" --silent
    Write-SetupLog "Go uninstalled" "SUCCESS"
}
