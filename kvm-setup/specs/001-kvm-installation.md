# Spec 001: KVM Installation

**Status: COMPLETE**

## Description
Automated KVM/QEMU setup for CachyOS/Arch Linux.

## Requirements
- Install qemu-full, virt-manager, libvirt and related tools
- Enable and start libvirtd service
- Configure libvirtd.conf permissions
- Add user to libvirt group

## Acceptance Criteria
- [x] Installs all required KVM packages
- [x] Enables and starts libvirtd.service
- [x] Configures permissions in libvirtd.conf
- [x] Adds current user to libvirt group
- [x] Documents VirtualBox coexistence

## Implementation Notes
Created `install.sh` with full setup. Note about logout requirement for group membership.
