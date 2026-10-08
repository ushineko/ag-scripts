# PowerShell Profile - Oh My Posh + Atuin

# Add user bin to PATH
$env:PATH = "$env:USERPROFILE\bin;$env:PATH"

# POSIX/MSYS tooling (bash, grep, sed, awk, make, xz, gcc, ...).
# Appended, not prepended: Windows find.exe/sort.exe/curl.exe/OpenSSH and
# Git for Windows' git.exe (Program Files\Git\cmd) keep precedence.
# Prefer MSYS2 (superset, pacman-extensible); fall back to Git for Windows'
# bundled MSYS. Only one msys usr\bin goes on PATH to avoid mixing runtimes.
$__posixDirs = if (Test-Path 'C:\msys64\usr\bin\bash.exe') {
    'C:\msys64\ucrt64\bin', 'C:\msys64\usr\bin'
} elseif (Test-Path "$env:ProgramFiles\Git\usr\bin\bash.exe") {
    "$env:ProgramFiles\Git\mingw64\bin", "$env:ProgramFiles\Git\usr\bin"
} else { @() }
$__pathParts = $env:PATH -split ';'
foreach ($d in $__posixDirs) {
    if ((Test-Path $d) -and ($__pathParts -notcontains $d)) { $env:PATH = "$env:PATH;$d" }
}
Remove-Variable __posixDirs, __pathParts, d -ErrorAction SilentlyContinue

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

# eza aliases - modern ls replacement
# Preserve original PowerShell ls as lsps
function lsps { Get-ChildItem @args }

# Remove built-in aliases first
Remove-Item Alias:ls -Force -ErrorAction SilentlyContinue
Remove-Item Alias:dir -Force -ErrorAction SilentlyContinue

# Override ls and dir with eza functions
function global:ls { eza -la --icons @args }
function global:dir { eza -la --icons @args }
