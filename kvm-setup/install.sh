#!/bin/bash
set -e

echo "Starting KVM Setup..."

# Install necessary packages
echo "Installing KVM packages (qemu-full, virt-manager, libvirt, etc.)..."
sudo pacman -S --needed qemu-full virt-manager virt-viewer dnsmasq vde2 bridge-utils openbsd-netcat libvirt iptables-nft

# Enable and start libvirtd service
echo "Enabling and starting libvirtd..."
sudo systemctl enable --now libvirtd

# Configure libvirtd.conf to allow user access
# We use sed to uncomment the lines if they are commented out
echo "Configuring /etc/libvirt/libvirtd.conf..."
sudo sed -i 's/^#unix_sock_group = "libvirt"/unix_sock_group = "libvirt"/' /etc/libvirt/libvirtd.conf
sudo sed -i 's/^#unix_sock_rw_perms = "0770"/unix_sock_rw_perms = "0770"/' /etc/libvirt/libvirtd.conf

# Start and autostart the default network
echo "Starting and enabling 'default' network..."
sudo virsh net-start default || echo "Default network already started or failed to start."
sudo virsh net-autostart default || echo "Failed to enable autostart for default network."

# Add the current user to the libvirt group
echo "Adding user '$USER' to the libvirt group..."
sudo usermod -aG libvirt "$USER"

# Check for nested virtualization (optional, good for performance if running inside another VM, but native usually has it on)
# Intel
if [ -f /sys/module/kvm_intel/parameters/nested ]; then
    echo "Checking Intel nested virtualization..."
    cat /sys/module/kvm_intel/parameters/nested
fi
# AMD
if [ -f /sys/module/kvm_amd/parameters/nested ]; then
    echo "Checking AMD nested virtualization..."
    cat /sys/module/kvm_amd/parameters/nested
fi

echo ""
echo "----------------------------------------------------------------"
echo "Installation complete!"
echo "NOTE: You are running this system with VirtualBox potentially installed."
echo "Please remember: Only run ONE hypervisor at a time to avoid conflicts."
echo "Stop all VirtualBox VMs before using KVM, and vice-versa."
echo ""
echo "You may need to LOG OUT and LOG BACK IN for the group membership to apply!"
echo "Alternatively, run 'newgrp libvirt' in your current shell."
echo "----------------------------------------------------------------"
