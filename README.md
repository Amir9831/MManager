# MManager

Modular Minecraft server manager for Ubuntu 22.04+.

## Development status
This repository contains an early development foundation: interactive recovery CLI, Core API, SQLite registry, TCP/UDP port probe, responsive purple dashboard, preflight installer and CI. It is **not yet a production Minecraft hosting panel**. Game runtime adapters, panel authentication, live console, backup/restore, transactional port reservations and signed self-update/rollback are not complete. The installer intentionally makes no system changes.

## Development
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -e .
Mmanager
```

## Local panel preview
Run Core API on 127.0.0.1:8765 and static panel on 127.0.0.1:8766 (see systemd unit examples). To access remotely, use SSH tunnels for both ports; do not expose either service publicly.

## Host layout target
- `/opt/mmanager` — application code
- `/etc/mmanager` — configuration and secrets
- `/var/lib/mmanager` — database, worlds and backups
- `/var/log/mmanager` — logs

See `docs/` and `SECURITY.md`.
