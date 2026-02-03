# Windows Setup Scripts

PowerShell scripts to automate the setup of a Windows development environment. Installs and configures development tools, shells, and applications with idempotent, scriptable installation.

## Table of Contents

- [Quick Start](#quick-start)
- [Components](#components)
- [Usage](#usage)
- [Configuration](#configuration)
- [Testing](#testing)
- [Uninstallation](#uninstallation)
- [Project Structure](#project-structure)

## Quick Start

### One-Liner Installation (Fresh System)

Run this in PowerShell on a fresh Windows system:

```powershell
irm https://raw.githubusercontent.com/ushineko/ag-scripts/main/windows-setup-scripts/bootstrap.ps1 | iex
```

### Local Installation

If you already have the repository:

```powershell
.\install.ps1
```

### Dry Run

Preview what would be installed without making changes:

```powershell
.\install.ps1 -DryRun
```

## Components

| Component | Description | Install Method |
|-----------|-------------|----------------|
| PowerShell 7 | Modern cross-platform PowerShell | winget |
| Git for Windows | Git version control | winget |
| MSYS2 | Unix-like environment for Windows | GitHub releases |
| MSYS2 Packages | git, make, vim, zsh | pacman |
| Oh My Posh | Prompt theme engine | winget |
| Atuin | Shell history manager | winget |
| Neovim | Text editor | winget |
| NvChad | Neovim configuration framework | Config copy |
| Go | Go programming language | winget |
| Miniforge3 | Conda distribution (conda-forge) | GitHub releases |
| Claude Code | AI coding assistant CLI | npm |
| Antigravity | Application | antigravity.google |
| clockwork-orange | Application | GitHub releases |
| Hack Nerd Font | Terminal font with icons | GitHub releases |
| Windows Terminal | Terminal profiles | Config merge |

## Usage

### Full Installation

```powershell
.\install.ps1
```

### Install Specific Components

```powershell
.\install.ps1 -Components msys2,neovim,fonts
```

Available components: `prerequisites`, `powershell7`, `git`, `fonts`, `msys2`, `oh-my-posh`, `atuin`, `neovim`, `golang`, `miniforge`, `claude-code`, `antigravity`, `clockwork-orange`, `terminal`

### Force Reinstallation

```powershell
.\install.ps1 -Force
```

### Bootstrap with Parameters

```powershell
# Dry run via bootstrap
irm https://raw.githubusercontent.com/ushineko/ag-scripts/main/windows-setup-scripts/bootstrap.ps1 | iex
Install-DevEnv -DryRun

# Specific components via bootstrap
Install-DevEnv -Components msys2,neovim
```

## Configuration

### Shell Configurations

The installer copies shell configuration files to `%USERPROFILE%`:

- `.bashrc` - Bash configuration with Oh My Posh, Atuin, nvim aliases
- `.zshrc` - Zsh configuration with same tools
- `.profile` - Login shell settings
- `.bash-preexec.sh` - Bash preexec hooks for Atuin

### Oh My Posh Theme

Custom PowerLevel10k-style theme at `~/.config/oh-my-posh/powerlevel10k_rainbow.omp.json`

### Neovim (NvChad)

Full NvChad configuration with:
- `onedark` theme
- claudecode.nvim integration
- LSP for HTML/CSS
- Stylua formatting

### Windows Terminal Profiles

Custom profiles added:
- **MSYS2** - Zsh shell in MSYS2 environment
- **Claude Code** - Direct Claude CLI access

## Testing

### Verify Download URLs

Check that all download URLs are still valid:

```powershell
.\tests\test-download-urls.ps1
```

### Verify Installation

Check that all components are installed correctly:

```powershell
.\tests\test-installation.ps1
```

## Uninstallation

### Remove All Components (Keep Configs)

```powershell
.\uninstall.ps1
```

### Remove All Components and Configs

```powershell
.\uninstall.ps1 -RemoveConfigs
```

### Remove Specific Components

```powershell
.\uninstall.ps1 -Components msys2,neovim
```

## Project Structure

```
windows-setup-scripts/
├── README.md                 # This file
├── bootstrap.ps1             # Remote one-liner installer
├── install.ps1               # Main installer script
├── uninstall.ps1             # Uninstaller script
├── lib/
│   └── common.ps1            # Shared utility functions
├── modules/
│   ├── prerequisites.ps1     # Winget, Node.js checks
│   ├── powershell7.ps1       # PowerShell 7
│   ├── git.ps1               # Git for Windows
│   ├── fonts.ps1             # Hack Nerd Font
│   ├── msys2.ps1             # MSYS2 + packages
│   ├── oh-my-posh.ps1        # Oh My Posh + theme
│   ├── atuin.ps1             # Atuin + config
│   ├── neovim.ps1            # Neovim + NvChad
│   ├── golang.ps1            # Go
│   ├── miniforge.ps1         # Miniforge3
│   ├── claude-code.ps1       # Claude Code CLI
│   ├── antigravity.ps1       # Antigravity app
│   ├── clockwork-orange.ps1  # clockwork-orange
│   └── terminal.ps1          # Windows Terminal profiles
├── configs/
│   ├── shell/                # .bashrc, .zshrc, etc.
│   ├── oh-my-posh/           # Prompt theme
│   ├── atuin/                # Atuin config
│   ├── nvim/                 # NvChad config
│   ├── claude/               # CLAUDE.md
│   ├── miniforge/            # .condarc
│   ├── terminal/             # Windows Terminal profiles
│   └── download-urls.json    # Centralized download URLs
└── tests/
    ├── test-download-urls.ps1    # URL validation
    └── test-installation.ps1     # Installation verification
```

## Idempotency

All installation scripts are idempotent:
- Running twice produces the same result
- Existing installations are detected and skipped (unless `-Force`)
- Config files are backed up before overwriting

## Backup Strategy

Before overwriting any configuration file, the installer creates a timestamped backup:

```
~/.bashrc.backup.20260203_143022
```

Backups are preserved during uninstallation unless explicitly removed.

## Requirements

- Windows 10/11
- PowerShell 5.1 or higher (comes with Windows)
- Internet connection for downloads
- Administrator privileges may be required for some components

## Troubleshooting

### winget not found

Install "App Installer" from the Microsoft Store:
https://www.microsoft.com/store/productId/9NBLGGH4NNS1

### Font not showing in terminal

1. Restart Windows Terminal after font installation
2. Verify font is installed: Settings > Personalization > Fonts > Search "Hack"
3. Manually select "Hack Nerd Font Mono" in terminal profile settings

### PATH not updated

1. Close and reopen terminal
2. Or run: `Refresh-EnvironmentPath` (from common.ps1)

### Neovim plugins not loading

Run `:Lazy sync` in Neovim to manually trigger plugin installation.

## Changelog

### 1.0.1
- Fixed GitHub URLs using incorrect username (nverenin -> ushineko)

### 1.0.0
- Initial release with full development environment setup

## Version

1.0.1

## License

MIT
