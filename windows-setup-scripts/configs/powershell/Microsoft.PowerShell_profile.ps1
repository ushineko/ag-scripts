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

# eza aliases (modern ls replacement)
if (Get-Command eza -ErrorAction SilentlyContinue) {
    function ls { eza --color=always --group-directories-first --icons @args }
    function ll { eza --color=always --group-directories-first --icons -la @args }
    function la { eza --color=always --group-directories-first --icons -a @args }
    function lt { eza --color=always --group-directories-first --icons -T @args }
    function l { eza --color=always --group-directories-first --icons -l @args }
    function tree { eza --color=always --group-directories-first --icons -T @args }
}
