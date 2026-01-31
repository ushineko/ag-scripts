# Spec 001: VPN Binding

**Status: COMPLETE**

## Description
Ensure VPN connection before launching qBittorrent.

## Requirements
- Connect to specified NetworkManager VPN profile
- Verify public IP matches expected location
- Retry logic for connection delays
- Abort if verification fails

## Acceptance Criteria
- [x] Connects to configured VPN profile
- [x] Verifies IP location via ip-api.com
- [x] 3 retry attempts for initial delays
- [x] Aborts launch if verification fails
- [x] Configurable VPN name and expected location

## Implementation Notes
Created `qbittorrent_vpn_wrapper.py`. Retry logic added in v1.0.2.
