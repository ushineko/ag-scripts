# Docker Setup Script

A simple, automated setup script to get Docker running on Arch-based systems (optimized for CachyOS/Arch).

## Table of Contents
- [Features](#features)
- [Usage](#usage)
- [Post-Install](#post-install)
- [Changelog](#changelog)

## Features
- **Auto-Installation**: Installs `docker` and `docker-buildx` via `pacman`.
- **Service Management**: Enables and starts the `docker` systemd service.
- **Group Management**: Safely adds the current user to the `docker` group to allow rootless command execution.
- **Verification**: Runs a test container (`hello-world`) to verify the installation works.
- **Immediate Usage**: Uses `sg` (setgroup) to verify access immediately without requiring a logout.

## Usage
Run the script as your normal user. It will ask for `sudo` password when needed.
```bash
./setup_docker.sh
```

## Post-Install
If you just installed Docker, you may need to apply the group changes to your current shell:
```bash
newgrp docker
```
Or simply log out and back in.

## Changelog

### v1.0.0
- Initial release
- Auto-installation via pacman
- Service management and group setup
- Installation verification with hello-world container
