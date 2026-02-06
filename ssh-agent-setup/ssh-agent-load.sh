#!/bin/bash
# ssh-agent-load.sh - Load SSH keys from config file into ssh-agent
# Uses ksshaskpass to retrieve passphrases from KWallet
#
# Config file format (one key path per line, # for comments):
#   ~/.ssh/id_rsa
#   ~/.ssh/id_ed25519
#   # ~/.ssh/disabled_key

set -euo pipefail

CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/ssh-agent-setup/keys.conf"
LOG_TAG="ssh-agent-load"

log() {
    logger -t "$LOG_TAG" "$1" 2>/dev/null || true
}

if [[ ! -f "$CONFIG" ]]; then
    log "Config file not found: $CONFIG"
    exit 0
fi

loaded=0
failed=0

while IFS= read -r key || [[ -n "$key" ]]; do
    # Skip comments and empty lines
    [[ "$key" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${key// }" ]] && continue

    # Expand ~ to $HOME
    expanded="${key/#\~/$HOME}"

    # Trim whitespace
    expanded="${expanded#"${expanded%%[![:space:]]*}"}"
    expanded="${expanded%"${expanded##*[![:space:]]}"}"

    if [[ ! -f "$expanded" ]]; then
        log "Key file not found: $expanded"
        ((failed++)) || true
        continue
    fi

    if ssh-add "$expanded" 2>/dev/null; then
        log "Loaded key: $expanded"
        ((loaded++)) || true
    else
        log "Failed to load key: $expanded"
        ((failed++)) || true
    fi
done < "$CONFIG"

log "Finished: $loaded loaded, $failed failed"
