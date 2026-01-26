# KVM Setup for CachyOS

This project provides scripts to easily install and configure KVM (Kernel-based Virtual Machine) on CachyOS (Arch Linux).

## Coexistence with VirtualBox

**IMPORTANT**: You likely have VirtualBox installed. 
- You can keep both installed on the same system.
- **DO NOT** run VMs from both hypervisors simultaneously if you want hardware acceleration (you generally do).
- Ensure VirtualBox VMs are powered off before starting KVM VMs, and vice versa.

## Installation

Run the installation script:

```bash
./install.sh
```

This will:
1. Install `qemu-full`, `virt-manager`, `libvirt`, and related tools.
2. Enable and start the `libvirtd` service.
3. Configure `libvirtd.conf` permissions.
4. Add your user to the `libvirt` group.

**Note**: You may need to log out and log back in (or restart) for the group membership to take effect before you can run `virt-manager` without password prompts.

## Uninstallation

To remove the packages and disable the service:

```bash
./uninstall.sh
```

## Usage

Launch **Virtual Machine Manager** from your application menu or run:
```bash
virt-manager
```
