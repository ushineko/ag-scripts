# PowerShell Profile - Oh My Posh + Atuin

# Initialize Oh My Posh
$ompConfig = "$env:USERPROFILE\.config\oh-my-posh\powerlevel10k_rainbow.omp.json"
if (Test-Path $ompConfig) {
    oh-my-posh init pwsh --config $ompConfig | Invoke-Expression
}

# Initialize Atuin (if available)
if (Get-Command atuin -ErrorAction SilentlyContinue) {
    Invoke-Expression (& { (atuin init powershell) -join "`n" })
}

# Aliases
Set-Alias -Name vi -Value nvim -ErrorAction SilentlyContinue
Set-Alias -Name vim -Value nvim -ErrorAction SilentlyContinue
