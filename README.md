# MManager

Minecraft server manager for Ubuntu 22.04 / 24.04 / 26.04.

## One-command install

```bash
curl -fsSL https://raw.githubusercontent.com/Amir9831/MManager/main/install.sh | sudo bash
```

Admin credentials: `/root/mmanager-admin-credentials.txt` (0600). Panel: `http://127.0.0.1:8766`. Remote access only via SSH tunnel:

```bash
ssh -L 8766:127.0.0.1:8766 -L 8765:127.0.0.1:8765 USER@SERVER
```

## Implemented

Interactive `Mmanager` CLI; Argon2id login and bearer auth; Java Vanilla and Paper downloads; Paper-based Geyser/Floodgate crossplay; SQLite registry with TCP/UDP port uniqueness; systemd server lifecycle running unprivileged; logs; compressed, server-pausing backups and guarded restore; responsive purple web dashboard.

## Not yet implemented

Bedrock Dedicated Server, RCON commands/live interactive console, player moderation, CPU/RAM telemetry, plugin manager, signed self-updater/rollback and automated firewall configuration. The public panel is protected by a random URL path and Argon2id login; use HTTPS via a trusted reverse proxy for Internet-facing deployments. This is an early functional release, not a claim of zero defects. See SECURITY.md and docs/INSTALL.md.
