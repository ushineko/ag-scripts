#Requires -Version 5.1
<#
.SYNOPSIS
    Tests that all download URLs are reachable
.DESCRIPTION
    Validates that download URLs in configs/download-urls.json are still valid.
    For GitHub releases, verifies that assets matching expected patterns exist.
    Run this periodically to catch broken links before users encounter them.
.EXAMPLE
    .\tests\test-download-urls.ps1
#>

$ScriptRoot = Split-Path -Parent $PSScriptRoot

# Load common functions
. "$ScriptRoot\lib\common.ps1"

function Test-GitHubReleaseAssets {
    param(
        [string]$Repo,
        [string]$Pattern
    )

    try {
        $apiUrl = "https://api.github.com/repos/$Repo/releases/latest"
        $release = Invoke-RestMethod -Uri $apiUrl -Headers @{ "User-Agent" = "Windows-Setup-Scripts-Test" } -TimeoutSec 30

        $matchingAssets = $release.assets | Where-Object { $_.name -like $Pattern }

        if ($matchingAssets) {
            return @{
                Success = $true
                Version = $release.tag_name
                Asset = ($matchingAssets | Select-Object -First 1).name
            }
        } else {
            return @{
                Success = $false
                Error = "No assets match pattern: $Pattern"
                AvailableAssets = ($release.assets | ForEach-Object { $_.name }) -join ", "
            }
        }
    } catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
        }
    }
}

function Test-WebUrl {
    param(
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -Method Head -UseBasicParsing -TimeoutSec 30 -MaximumRedirection 5
        return @{
            Success = $true
            StatusCode = $response.StatusCode
        }
    } catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
        }
    }
}

function Main {
    Write-Host ""
    Write-Host "  Download URL Verification" -ForegroundColor Cyan
    Write-Host "  =========================" -ForegroundColor Cyan
    Write-Host ""

    $configPath = "$ScriptRoot\configs\download-urls.json"

    if (-not (Test-Path $configPath)) {
        Write-Host "  ERROR: Config file not found: $configPath" -ForegroundColor Red
        return 1
    }

    $config = Get-Content -Path $configPath -Raw | ConvertFrom-Json
    $results = @()
    $failed = 0

    foreach ($prop in $config.PSObject.Properties) {
        $name = $prop.Name
        $settings = $prop.Value

        Write-Host "  Testing: $name... " -NoNewline

        if ($settings.source -match "api.github.com") {
            # GitHub release
            $repo = $settings.source -replace "https://api.github.com/repos/", "" -replace "/releases/latest", ""
            $result = Test-GitHubReleaseAssets -Repo $repo -Pattern $settings.pattern

            if ($result.Success) {
                Write-Host "OK" -ForegroundColor Green -NoNewline
                Write-Host " (v$($result.Version), $($result.Asset))"
            } else {
                Write-Host "FAILED" -ForegroundColor Red
                Write-Host "    Error: $($result.Error)" -ForegroundColor Yellow
                if ($result.AvailableAssets) {
                    Write-Host "    Available: $($result.AvailableAssets)" -ForegroundColor Yellow
                }
                $failed++
            }
        } else {
            # Regular URL
            $result = Test-WebUrl -Url $settings.source

            if ($result.Success) {
                Write-Host "OK" -ForegroundColor Green -NoNewline
                Write-Host " (HTTP $($result.StatusCode))"
            } else {
                Write-Host "FAILED" -ForegroundColor Red
                Write-Host "    Error: $($result.Error)" -ForegroundColor Yellow
                $failed++
            }
        }

        $results += @{
            Name = $name
            Success = $result.Success
            Details = $result
        }
    }

    Write-Host ""
    Write-Host "  =========================" -ForegroundColor Cyan

    if ($failed -eq 0) {
        Write-Host "  All download URLs are valid" -ForegroundColor Green
        return 0
    } else {
        Write-Host "  $failed URL(s) failed verification" -ForegroundColor Red
        Write-Host ""
        Write-Host "  Action required:" -ForegroundColor Yellow
        Write-Host "  Update configs/download-urls.json with working URLs" -ForegroundColor Yellow
        return 1
    }
}

exit (Main)
