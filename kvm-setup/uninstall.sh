#!/bin/bash
set -e

echo "Uninstalling KVM packages..."

# Stop and disable service
echo "Stopping libvirtd..."
sudo systemctl disable --now libvirtd || echo "libvirtd was not running or not found."

# Remove packages
# Using -Rns to remove dependencies that are not required by other packages and configuration files
echo "Removing packages..."
sudo pacman -Rns qemu-full virt-manager virt-viewer dnsmasq vde2 bridge-utils openbsd-netcat libvirt iptables-nft

echo "Uninstallation complete."
echo "Note: Users were not removed from the 'libvirt' group manually. You can run 'sudo gpasswd -d $USER libvirt' if desired."
