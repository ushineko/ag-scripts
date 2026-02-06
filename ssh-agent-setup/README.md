# SSH Agent Auto-Load Setup

Automatically load SSH keys into ssh-agent on Plasma desktop login using KWallet for secure passphrase storage.

**Version**: 1.0.0

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Uninstallation](#uninstallation)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)

---

## Overview

This utility configures your system to automatically load SSH private keys after logging into your Plasma desktop session. Passphrases are stored securely in KWallet and retrieved silently on subsequent logins.

**Features:**
- Automatic key loading on graphical session start
- Secure passphrase storage via KWallet (AES-256 encrypted)
- Configurable list of SSH keys to load
- One-time passphrase prompt per key (stored in KWallet)
- Works with both passphrase-protected and passphrase-less keys
- Silent operation after initial setup

---

## How It Works

1. **On Login**: PAM module (`pam_kwallet5`) unlocks your KWallet using your login password
2. **After Graphical Session Starts**: systemd user service triggers the loader script
3. **Loader Script**: Reads configured keys from `~/.config/ssh-agent-setup/keys.conf`
4. **For Each Key**: `ssh-add` runs with `SSH_ASKPASS=ksshaskpass`
   - Keys without passphrases are added directly (no prompt)
   - Keys with passphrases: ksshaskpass retrieves from KWallet (or prompts if first time)
5. **Result**: SSH keys available in your session without manual intervention

---

## Prerequisites

**Required packages:**

```bash
# Arch/CachyOS
sudo pacman -S ksshaskpass openssh

# The following are usually installed with Plasma:
# kwallet, kwallet-pam
```

**System requirements:**
- Plasma desktop environment (KDE)
- systemd (user session support)
- KWallet configured and unlocked on login (default Plasma behavior)

---

## Installation

```bash
# Clone or navigate to the repository
cd ssh-agent-setup

# Preview what will be installed
./install.sh --dry-run

# Install
./install.sh
```

**Files installed:**

| Location | Purpose |
|----------|---------|
| `~/.local/bin/ssh-agent-load.sh` | Loader script |
| `~/.config/systemd/user/ssh-add.service` | systemd user service |
| `~/.config/environment.d/ssh-askpass.conf` | SSH_ASKPASS environment |
| `~/.config/ssh-agent-setup/keys.conf` | List of keys to load |

---

## Configuration

Edit `~/.config/ssh-agent-setup/keys.conf` to specify which SSH keys to load:

```bash
# SSH keys to load on login (one per line)
# Lines starting with # are ignored
# Paths can use ~ for home directory

~/.ssh/id_rsa
~/.ssh/id_ed25519
~/.ssh/work_key

# Commented-out keys are not loaded:
# ~/.ssh/old_key
```

---

## Usage

### First Login After Installation

1. Log out and log back in
2. KWallet will prompt for each key's passphrase (one time only)
3. Enter the passphrase and optionally save it in KWallet
4. Verify keys are loaded: `ssh-add -l`

### Subsequent Logins

Keys are loaded automatically with no prompts.

### Manual Testing (Without Relogging)

```bash
# Start the service manually
systemctl --user start ssh-add.service

# Check loaded keys
ssh-add -l
```

### Service Status

```bash
# Check if service is enabled
systemctl --user status ssh-add.service

# View logs
journalctl --user -u ssh-add.service
```

---

## Uninstallation

```bash
# Preview what will be removed
./uninstall.sh --dry-run

# Uninstall (removes everything including config)
./uninstall.sh

# Uninstall but keep your keys.conf
./uninstall.sh --keep-config
```

**Note**: To remove stored passphrases from KWallet:
1. Open KWalletManager
2. Navigate to "Passwords" → "ksshaskpass"
3. Delete entries for keys you no longer want stored

---

## Troubleshooting

### Keys not loading after login

1. **Check service status:**
   ```bash
   systemctl --user status ssh-add.service
   ```

2. **Check logs:**
   ```bash
   journalctl --user -u ssh-add.service -n 20
   ```

3. **Verify SSH_ASKPASS is set:**
   ```bash
   echo $SSH_ASKPASS
   # Should output: ksshaskpass
   ```

4. **Test manually:**
   ```bash
   SSH_ASKPASS=ksshaskpass SSH_ASKPASS_REQUIRE=prefer ssh-add ~/.ssh/id_rsa
   ```

### KWallet not unlocking automatically

Ensure PAM is configured for KWallet:
```bash
# Check if pam_kwallet5 is in your PAM config
grep kwallet /etc/pam.d/sddm
```

If missing, the kwallet-pam package may not be installed or configured.

### "No such identity" errors

Verify the key paths in `~/.config/ssh-agent-setup/keys.conf` are correct:
```bash
# List your actual SSH keys
ls -la ~/.ssh/*.pub
```

### Passphrase prompts every time

This usually means KWallet isn't storing the passphrase:
1. Open KWalletManager
2. Check if entries exist under "ksshaskpass"
3. Try deleting and re-adding the passphrase

---

## Security Notes

**Passphrase Storage:**
- Passphrases are stored in KWallet, encrypted with AES-256
- KWallet is unlocked by your login password via PAM
- If someone has your login password, they can access your SSH keys

**Recommendations:**
- Use a strong login password
- Consider full disk encryption (LUKS) for additional protection
- For maximum security, use FIDO2/U2F hardware keys instead (see below)

**Hardware Key Alternative:**

For the most secure option, use SSH keys stored on hardware tokens:
```bash
# Generate a hardware-resident key (requires YubiKey or similar)
ssh-keygen -t ed25519-sk -O resident -O verify-required
```

This eliminates passphrase management entirely - the hardware device is the authentication.

---

## Changelog

### v1.0.0
- Initial release
- KWallet + ksshaskpass integration
- Configurable key list
- systemd user service for automatic loading
- Install/uninstall scripts with --dry-run support
