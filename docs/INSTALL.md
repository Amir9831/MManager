# Installation

```bash
curl -fsSL https://raw.githubusercontent.com/Amir9831/MManager/main/install.sh | sudo bash
```

Ubuntu 22.04, 24.04 or 26.04 with systemd. The installer creates an administrator password and a random, high-entropy panel path. After both services pass their health checks, a fresh installation prints the public panel URL including the port and path and displays the newly generated administrator password once. The password is also saved to `/root/mmanager-admin-credentials.txt` (mode 0600). Reinstallations and upgrades preserve the existing password and do not display it.

The public panel and its API are served on the same configured TCP port and are reachable only below the random path. The core API remains bound to loopback. Use `sudo Mmanager` → **Web panel management** to rotate the path, change the administrator password, or change the public panel port. The installer adds the TCP port to UFW when UFW is already active; allow it in the VPS/cloud firewall as well, if applicable.

Existing `/etc/mmanager` credentials and `/var/lib/mmanager` worlds/backups are preserved on reinstall. Reinstalling does not rotate an existing panel path or password. To uninstall MManager, run `sudo Mmanager`, select option 9, and type `DELETE` at the confirmation prompt. The uninstaller removes MManager services, binaries and configuration but deliberately preserves `/var/lib/mmanager` worlds and backups; review and remove `/var/lib/mmanager` manually only if you also intend to delete that data.
