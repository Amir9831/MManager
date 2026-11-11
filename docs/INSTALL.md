# Installation

```bash
curl -fsSL https://raw.githubusercontent.com/Amir9831/MManager/main/install.sh | sudo bash
```

Ubuntu 22.04, 24.04 or 26.04 with systemd. Installs Python, Java 21 (OpenJDK package or Eclipse Temurin fallback), an unprivileged account, isolated Python environment, systemd units, CLI and local-only panel. Existing `/etc/mmanager` credentials and `/var/lib/mmanager` worlds/backups are preserved on reinstall.

Credentials are saved to `/root/mmanager-admin-credentials.txt` mode 0600. For remote access, SSH-forward ports 8765 and 8766. Do not expose them directly.
