# Spec 002: Docker/Firewall Network Fix

**Status: COMPLETE**

## Description
Fix for KVM network issues caused by Docker or strict firewalls.

## Requirements
- Inject rules into DOCKER-USER chain
- Allow KVM traffic without breaking Docker
- Easy to run as sudo script

## Acceptance Criteria
- [x] `fix_network.sh` script created
- [x] Injects iptables rules for KVM traffic
- [x] Doesn't interfere with Docker configuration
- [x] Documents usage for network troubleshooting

## Implementation Notes
Added in v1.1.0. Solves internet access issues for VMs when Docker is installed.
