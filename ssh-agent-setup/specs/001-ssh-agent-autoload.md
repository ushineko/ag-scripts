# Spec 001: SSH Agent Auto-Load

## Overview

A setup script and systemd user service that automatically loads SSH private keys into ssh-agent on Plasma desktop login, using KWallet for secure passphrase storage.

## Problem Statement

- SSH keys with passphrases require manual `ssh-add` after each login
- Storing passphrases in plaintext is insecure
- Users want passwordless SSH workflow without sacrificing security

## Requirements

### Functional Requirements

- [x] Create systemd user service that runs ssh-add on graphical-session.target
- [x] Configure SSH_ASKPASS to use ksshaskpass
- [x] Store SSH key passphrase in KWallet via ksshaskpass prompt
- [x] Support multiple SSH keys (configurable list via keys.conf)
- [x] Provide install.sh that sets up the systemd service
- [x] Provide uninstall.sh that removes all configuration
- [x] Verify prerequisites (ksshaskpass) before setup

### Non-Functional Requirements

- [x] Works on Arch/CachyOS with Plasma 6
- [x] Silent operation (no GUI prompts after initial passphrase storage)
- [x] Keys loaded within 5 seconds of graphical session start
- [x] Clear documentation of what changes are made to the system

## Acceptance Criteria

- [x] After install + reboot, `ssh-add -l` shows loaded keys without manual intervention
- [x] No passphrase prompts appear after initial storage in KWallet
- [x] Uninstall completely reverses all changes
- [x] Works with standard ~/.ssh/id_rsa and ~/.ssh/id_ed25519 keys
- [x] Custom key paths can be configured via keys.conf
- [x] Script checks for and reports missing prerequisites
- [x] --dry-run flag shows what would be created without creating it

## Technical Design

### Files Created by Install

```
~/.local/bin/ssh-agent-load.sh          # loader script
~/.config/systemd/user/ssh-add.service  # systemd user service
~/.config/environment.d/ssh-askpass.conf # SSH_ASKPASS environment
~/.config/ssh-agent-setup/keys.conf     # configurable key list
```

### Config File Format

```bash
# SSH keys to load on login (one per line)
~/.ssh/id_rsa
~/.ssh/nixos
# ~/.ssh/disabled_key
```

### systemd User Service

- Type: oneshot
- After: graphical-session.target
- WantedBy: graphical-session.target
- Sets SSH_ASKPASS=ksshaskpass
- Executes loader script

### First-Run Behavior

1. ssh-add runs, triggers ksshaskpass
2. ksshaskpass prompts for passphrase via KWallet GUI
3. User enters passphrase once
4. KWallet stores it under "ksshaskpass" entry
5. Subsequent logins: passphrase retrieved silently

## File Structure

```
ssh-agent-setup/
├── README.md
├── install.sh
├── uninstall.sh
├── ssh-agent-load.sh
├── ssh-add.service
├── ssh-askpass.conf
├── keys.conf.template
├── specs/
│   └── 001-ssh-agent-autoload.md
└── tests/
    └── test_installation.sh
```

## Test Plan

- [x] install.sh creates all expected files
- [x] install.sh --dry-run shows actions without executing
- [x] install.sh fails gracefully if ksshaskpass not installed
- [x] systemd service enables successfully
- [x] uninstall.sh removes all created files
- [x] uninstall.sh is idempotent (can run multiple times)

## Status

**Status: COMPLETE**

---

## Notes

- Uses KWallet for secure passphrase storage (AES-256 encrypted)
- PAM module pam_kwallet5 auto-unlocks wallet on login
- Alternative: FIDO2/ed25519-sk keys eliminate passphrase management entirely
- TPM2 binding documented as optional enhancement in README
