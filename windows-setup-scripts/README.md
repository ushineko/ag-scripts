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
- [Idempotency](#idempotency)
- [Backup Strategy](#backup-strategy)
- [Requirements](#requirements)
- [Troubleshooting](#troubleshooting)
- [Changelog](#changelog)

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
| SSH Agent | Windows OpenSSH agent service | Service config |
| MSYS2 | Unix-like environment for Windows | GitHub releases |
| MSYS2 Packages | git, make, vim, zsh | pacman |
| Oh My Posh | Prompt theme engine | winget |
| Atuin | Shell history manager | winget |
| Neovim | Text editor | winget |
| NvChad | Neovim configuration framework | Config copy |
| Go | Go programming language | winget |
| eza | Modern ls replacement | winget |
| Miniforge3 | Conda distribution (conda-forge) | GitHub releases |
| Claude Code | AI coding assistant CLI | npm |
| Antigravity | Application | antigravity.google |
| clockwork-orange | Application | GitHub releases |
| Hack Nerd Font | Terminal font with icons | GitHub releases |
| Windows Terminal | Terminal profiles | Config merge |
| drag-translucency | Fade windows while dragging (AutoHotkey v2, autostart) | winget + config copy |

## Usage

### Full Installation

```powershell
.\install.ps1
```

### Install Specific Components

```powershell
.\install.ps1 -Components msys2,neovim,fonts
```

Available components: `prerequisites`, `powershell7`, `git`, `ssh-agent`, `fonts`, `msys2`, `oh-my-posh`, `atuin`, `neovim`, `golang`, `eza`, `miniforge`, `claude-code`, `antigravity`, `clockwork-orange`, `herdr`, `yazi`, `glow`, `lazygit`, `terminal`, `drag-translucency`

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

### SSH Agent

The installer configures the Windows OpenSSH Authentication Agent service:
- Service is set to start automatically
- Service is started immediately
- Shell configs alias `ssh` and `ssh-add` to Windows OpenSSH binaries

This allows SSH keys to be loaded once and reused across all shells (PowerShell, MSYS2, Git Bash).

**Adding SSH keys:**
```powershell
ssh-add ~/.ssh/id_ed25519
```

**Note:** May require administrator privileges to configure the service on first run.

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
│   ├── ssh-agent.ps1         # Windows SSH Agent service
│   ├── fonts.ps1             # Hack Nerd Font
│   ├── msys2.ps1             # MSYS2 + packages
│   ├── oh-my-posh.ps1        # Oh My Posh + theme
│   ├── atuin.ps1             # Atuin + config
│   ├── neovim.ps1            # Neovim + NvChad
│   ├── golang.ps1            # Go
│   ├── eza.ps1               # eza (ls replacement)
│   ├── miniforge.ps1         # Miniforge3
│   ├── claude-code.ps1       # Claude Code CLI
│   ├── antigravity.ps1       # Antigravity app
│   ├── clockwork-orange.ps1  # clockwork-orange
│   ├── terminal.ps1          # Windows Terminal profiles
│   └── drag-translucency.ps1 # Fade windows while dragging (AutoHotkey v2)
├── configs/
│   ├── shell/                # .bashrc, .zshrc, etc.
│   ├── oh-my-posh/           # Prompt theme
│   ├── atuin/                # Atuin config
│   ├── nvim/                 # NvChad config
│   ├── claude/               # CLAUDE.md
│   ├── miniforge/            # .condarc
│   ├── terminal/             # Windows Terminal profiles
│   ├── drag-translucency/    # drag-translucency.ahk
│   └── download-urls.json    # Centralized download URLs
└── tests/
    ├── test-download-urls.ps1    # URL validation
    └── test-installation.ps1     # Installation verification
```

## Idempotency

All installation scripts are idempotent and safe to re-run:

**Binary/Tool Installation:**
- Existing installations are detected and skipped
- Use `-Force` to reinstall/upgrade

**Configuration Files:**
- Existing config files are **NOT overwritten** by default (preserves user customizations)
- Re-running without `-Force` shows warnings for each existing config
- Use `-Force` to overwrite configs (automatic backup created first)

**Example re-run output:**
```
[WARNING] File exists (use -Force to overwrite): C:\Users\you\.bashrc
[WARNING] File exists (use -Force to overwrite): C:\Users\you\.zshrc
```

This is intentional behavior to prevent losing custom configurations.

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

### 1.5.0
- Added drag-translucency: fades a window while it is being dragged/resized via an AutoHotkey v2 WinEvent hook. Installs the AutoHotkey v2 runtime, deploys the script to `%LOCALAPPDATA%\drag-translucency\`, and autostarts it via a user Startup-folder shortcut. Migrated from the dotfiles repo (`setup/win11-kvm/`), which now references it here.

### 1.4.0
- Added eza: modern ls replacement with icons, colors, and tree view
- New eza aliases in all shells: `ls`, `ll`, `la`, `lt`, `l`, `tree`
- zsh includes fallback to standard ls if eza not installed

### 1.3.0
- Added git user configuration: prompts for user.name and user.email during setup (if not already configured)
- Added git SSH configuration: automatically configures git to use Windows OpenSSH (core.sshCommand)
- Fixed miniforge PATH: now adds Miniforge3 directories to system PATH after installation
- Miniforge PATH directories added: `C:\miniforge3`, `C:\miniforge3\Scripts`, `C:\miniforge3\Library\bin`

### 1.2.1
- Fixed clockwork-orange: now uses pinned release tag (v2.7.3) instead of latest to avoid dev builds
- Fixed clockwork-orange: added -Tag parameter support to Get-GitHubReleaseAsset
- Fixed atuin PATH: added cargo bin and winget package folder paths to shell configs
- Shell configs now search for atuin in winget package directories

### 1.2.0
- Added ssh-agent module: configures Windows OpenSSH Authentication Agent service
- Shell configs use Windows OpenSSH binaries for consistent SSH key handling across all shells

### 1.1.1
- Fixed Copy-ConfigFile: empty files are now overwritten (fixes PS7 profile not being populated)
- Fixed terminal module: profiles are now always updated on re-runs (ensures font settings stay correct)
- Simplified antigravity module: now only provides manual installation instructions

### 1.1.0
- Fixed fonts module: gracefully handle "file in use" errors when fonts already installed
- Fixed neovim module: no longer shows "config copied" when config already exists
- Fixed clockwork-orange: PATH and Start Menu shortcut now created even on re-runs
- Fixed oh-my-posh: robust Documents folder detection (handles OneDrive redirection)
- Fixed winget calls: use Start-Process with hidden window to prevent hanging
- Fixed MSYS2: configure HOME to use Windows user profile via nsswitch.conf
- Fixed package IDs: corrected case-sensitive winget IDs (Atuinsh.Atuin)
- Added PowerShell profile installation for both PS5 and PS7
- Added WinGet Links to PATH in shell configs
- Improved idempotency documentation
- Removed debug logging statements

### 1.0.1
- Fixed GitHub URLs using incorrect username (nverenin -> ushineko)

### 1.0.0
- Initial release with full development environment setup

## Version

1.5.0

## License

MIT
