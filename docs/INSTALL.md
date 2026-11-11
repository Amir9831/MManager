# Installation

```bash
curl -fsSL https://raw.githubusercontent.com/Amir9831/MManager/main/install.sh | sudo bash
```

Supported: Ubuntu 22.04, 24.04 and 26.04 with systemd. Installs Python, Java 21, an unprivileged service account, isolated Python environment, systemd units, CLI and local-only panel. Existing /etc/mmanager credentials and /var/lib/mmanager worlds/backups are preserved on reinstall.

Credentials are stored at `/root/mmanager-admin-credentials.txt` with mode 0600. For remote access, SSH-forward both ports 8765 and 8766. Do not expose them directly.
