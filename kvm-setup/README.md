# KVM Setup for CachyOS

This project provides scripts to easily install and configure KVM (Kernel-based Virtual Machine) on CachyOS (Arch Linux).

## Table of Contents
- [Coexistence with VirtualBox](#coexistence-with-virtualbox)
- [Installation](#installation)
- [Uninstallation](#uninstallation)
- [Troubleshooting Network](#troubleshooting-network)
- [Changelog](#changelog)

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

## Troubleshooting Network

If you have Docker or a strict firewall (like UFW) installed, it may block internet access for your VMs even if they have an IP address.

To fix this, run the network fix script:
```bash
sudo ./fix_network.sh
```

This script injects rules into the `DOCKER-USER` chain to allow KVM traffic without interfering with your Docker configuration.

## Changelog

### v1.1.0
- Added Docker/firewall network fix script (`fix_network.sh`)

### v1.0.0
- Initial release
- Automated QEMU/libvirt installation
- User group configuration
