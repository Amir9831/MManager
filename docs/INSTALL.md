# Installation

```bash
curl -fsSL https://raw.githubusercontent.com/Amir9831/MManager/main/install.sh | sudo bash
```

Ubuntu 22.04, 24.04 or 26.04 with systemd. The installer creates an administrator password and a random, high-entropy panel path. At successful completion it prints the public panel URL including the port and path. The administrator password is saved to `/root/mmanager-admin-credentials.txt` (mode 0600).

The public panel and its API are served on the same configured TCP port and are reachable only below the random path. The core API remains bound to loopback. Use `sudo Mmanager` → **Web panel management** to rotate the path, change the administrator password, or change the public panel port. After changing the port, allow that TCP port in the VPS/cloud firewall.

Existing `/etc/mmanager` credentials and `/var/lib/mmanager` worlds/backups are preserved on reinstall. Reinstalling does not rotate an existing panel path or password.
