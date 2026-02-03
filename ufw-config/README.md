# UFW/iptables Configuration for gateway-host

> **Note**: `gateway-host` is a placeholder for the actual hostname. Replace with your machine's hostname as needed.

This documents the firewall configuration for the main workstation, which acts as:
- A gateway/router for a Windows VM (192.168.86.0/24 subnet)
- A Pi-hole DNS server (via Docker)
- A VPN gateway (traffic can route through tun0)

## Network Topology

```
Internet
    |
[Router/Gateway 192.168.86.1]
    |
[eno2: 192.168.86.32] <-- This machine (gateway-host)
    |
    +-- Docker networks (172.17.0.0/16, 172.18.0.0/16, 172.19.0.0/16)
    |       +-- Pi-hole (172.19.0.2) - DNS on port 53, Web UI on 18080
    |       +-- Various dev containers
    |
    +-- virbr0 (192.168.122.1/24) - libvirt default network
    |
    +-- tun0 (when VPN active) - OpenVPN tunnel
```

## Key Configuration Files

| File | Purpose |
|------|---------|
| `/etc/default/ufw` | UFW defaults (forward policy, IPv6, etc.) |
| `/etc/ufw/sysctl.conf` | Kernel network settings (IP forwarding) |
| `/etc/ufw/before.rules` | Custom iptables rules (NAT, forwarding) |
| `/etc/ufw/after.rules` | Post-processing rules (noisy service filtering) |

## Critical Settings

### 1. Enable IP Forwarding

In `/etc/ufw/sysctl.conf`:
```
net/ipv4/ip_forward=1
```

### 2. Allow Routed Traffic

In `/etc/default/ufw`:
```
DEFAULT_FORWARD_POLICY="ACCEPT"
```

**This is the setting that breaks things if set to DROP** - it blocks all forwarded/routed traffic even if IP forwarding is enabled at the kernel level.

### 3. NAT Rules (in before.rules)

The NAT section in `/etc/ufw/before.rules` handles masquerading:

```
*nat
:POSTROUTING ACCEPT [0:0]

# Masquerade traffic from VM network going out to non-local destinations
-A POSTROUTING -s 192.168.86.0/24 ! -d 192.168.86.0/24 -o eno2 -j MASQUERADE

# Masquerade traffic going out the VPN tunnel
-A POSTROUTING -o tun0 -j MASQUERADE

COMMIT
```

### 4. Forwarding Rules (in before.rules)

In the `*filter` section of `/etc/ufw/before.rules`:

```
# Windows VM forwarding (192.168.86.0/24 on eno2)
# Allow VM network to initiate outbound connections
-A ufw-before-forward -i eno2 -s 192.168.86.0/24 -j ACCEPT

# VPN forwarding (eno2 <-> tun0)
# Allow traffic from eno2 to go out the VPN tunnel
-A ufw-before-forward -i eno2 -o tun0 -j ACCEPT
```

## UFW Rules (Ports)

```
53/tcp                     ALLOW IN    Anywhere      # DNS (Pi-hole)
53/udp                     ALLOW IN    Anywhere      # DNS (Pi-hole)
18080/tcp                  ALLOW IN    Anywhere      # Pi-hole Web UI
22                         ALLOW IN    Anywhere      # SSH
```

## Setup From Scratch

If rebuilding, run these commands:

```bash
# 1. Enable UFW
sudo ufw enable

# 2. Set default policies
sudo ufw default allow incoming
sudo ufw default allow outgoing
sudo ufw default allow routed    # CRITICAL for forwarding

# 3. Allow required ports
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 53/tcp      # DNS
sudo ufw allow 53/udp      # DNS
sudo ufw allow 18080/tcp   # Pi-hole web UI

# 4. Enable IP forwarding in /etc/ufw/sysctl.conf
# Uncomment: net/ipv4/ip_forward=1

# 5. Set forward policy in /etc/default/ufw
# Change: DEFAULT_FORWARD_POLICY="ACCEPT"

# 6. Add NAT and forwarding rules to /etc/ufw/before.rules
# (See before.rules.backup in this directory)

# 7. Reload
sudo ufw reload
```

## Troubleshooting

### Traffic not forwarding (but DNS works)

**Symptom**: DNS lookups work (Pi-hole responds), but web traffic doesn't flow.

**Cause**: `DEFAULT_FORWARD_POLICY="DROP"` in `/etc/default/ufw`

**Fix**:
```bash
sudo sed -i 's/DEFAULT_FORWARD_POLICY="DROP"/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw
sudo ufw reload
```

**Why DNS works**: DNS queries go directly TO the machine (port 53 is allowed incoming). Web traffic needs to be FORWARDED/ROUTED through the machine, which is blocked by the routed policy.

### Check current status

```bash
# UFW status with policies
sudo ufw status verbose

# Check if forwarding is enabled at kernel level
cat /proc/sys/net/ipv4/ip_forward   # Should be 1

# Check NAT rules
sudo iptables -t nat -L -v -n

# Check forward chain
sudo iptables -L FORWARD -v -n
```

### Docker interference

Docker adds its own iptables rules. If Docker is installed after UFW is configured, the rules may conflict. Current Docker-related chains:
- DOCKER
- DOCKER-USER
- DOCKER-FORWARD
- DOCKER-BRIDGE

These are managed by Docker and generally coexist with UFW, but be aware they exist.

## Backup Files

This directory contains backups of the config files:
- `default-ufw.backup` - /etc/default/ufw
- `sysctl.conf.backup` - /etc/ufw/sysctl.conf
- `before.rules.backup` - /etc/ufw/before.rules
- `after.rules.backup` - /etc/ufw/after.rules
