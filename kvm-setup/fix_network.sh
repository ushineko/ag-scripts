#!/bin/bash
# Fix KVM/Libvirt Network Connectivity (Docker/UFW conflict)
# This script injects rules into the DOCKER-USER chain which Docker processes first.

set -e

# libvirt default network range
NETWORK="192.168.122.0/24"
INTERFACE="virbr0"

echo "Applying KVM network fix..."

# 1. Enable IP Forwarding
echo "Ensuring IP forwarding is enabled..."
sudo sysctl -w net.ipv4.ip_forward=1

# 2. Add MASQUERADE rule if missing
echo "Checking NAT rules..."
if ! sudo iptables -t nat -C POSTROUTING -s "$NETWORK" ! -d "$NETWORK" -j MASQUERADE 2>/dev/null; then
    echo "Adding MASQUERADE rule for $NETWORK..."
    sudo iptables -t nat -I POSTROUTING -s "$NETWORK" ! -d "$NETWORK" -j MASQUERADE
else
    echo "MASQUERADE rule already exists."
fi

# 3. Add FORWARD rules to DOCKER-USER chain
# This chain is processed BEFORE Docker's own rules and is safe from being clobbered.
echo "Checking FORWARD rules in DOCKER-USER..."

if ! sudo iptables -C DOCKER-USER -i "$INTERFACE" -j ACCEPT 2>/dev/null; then
    echo "Adding rule to allow outbound traffic from $INTERFACE..."
    sudo iptables -I DOCKER-USER -i "$INTERFACE" -j ACCEPT
fi

if ! sudo iptables -C DOCKER-USER -o "$INTERFACE" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
    echo "Adding rule to allow inbound/established traffic to $INTERFACE..."
    sudo iptables -I DOCKER-USER -o "$INTERFACE" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
fi

echo "Done! The Windows 11 VM should now have internet access."
echo "If network is still not working, try restarting the VM or running: sudo systemctl restart libvirtd"
