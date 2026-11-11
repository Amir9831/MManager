# MManager

Minecraft server manager for Ubuntu 22.04 / 24.04 / 26.04.

## One-command installation

```bash
curl -fsSL https://raw.githubusercontent.com/Amir9831/MManager/main/install.sh | sudo bash
```

Admin credentials are generated once at `/root/mmanager-admin-credentials.txt` (0600). Panel: `http://127.0.0.1:8766`. Remote access must use SSH forwarding:

```bash
ssh -L 8766:127.0.0.1:8766 -L 8765:127.0.0.1:8765 USER@SERVER
```

## Implemented in 0.2

- Interactive `Mmanager` recovery CLI.
- FastAPI Core API with Argon2id password hash and bearer-token authentication.
- Java Vanilla and Paper server download/provisioning.
- Paper crossplay via Geyser and Floodgate plugin download.
- SQLite registry with unique TCP port index.
- Per-server systemd template running as unprivileged `mmanager`.
- Start/stop/restart, journal logs, compressed backups and guarded restore.
- Responsive purple web dashboard.

## Not implemented yet

Bedrock Dedicated Server, RCON console/commands, player moderation, CPU/RAM telemetry, plugin manager, signed update/automatic rollback and full firewall automation. This is a functional development release, not a guarantee of zero defects. The web/API bind to loopback only. Review SECURITY.md before production use.
