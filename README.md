# MManager

Minecraft server manager for Ubuntu 22.04 / 24.04 / 26.04.

## One-command install

```bash
curl -fsSL https://raw.githubusercontent.com/Amir9831/MManager/main/install.sh | sudo bash
```

Admin credentials: `/root/mmanager-admin-credentials.txt` (0600). After installation, the installer prints the public panel URL with its random path and port. Use `Mmanager` → **Web panel management** to change the path, administrator password, or port. The panel and its API share the same public port; the core API remains loopback-only.

## مستندات فارسی\n\nراهنمای فارسی نصب، دسترسی عمومی، مدیریت Path/رمز/پورت و نکات امنیتی: [docs/FA.md](docs/FA.md).\n\n## Implemented

Interactive `Mmanager` CLI with an in-CLI updater; Argon2id login and bearer auth; single-server management for Java Vanilla/Paper, Bedrock Dedicated Server, and Paper + Geyser/Floodgate cross-play; live release catalogs; bundled Java/Bedrock/Geyser configuration templates; editable server.properties; systemd lifecycle; journal logs; compressed, server-pausing backups and guarded restore; responsive single-server web dashboard.

## Not yet implemented

RCON commands/live interactive console, player moderation, CPU/RAM telemetry, plugin manager, atomic Minecraft server binary updates/rollback and automated game-port firewall configuration. The public panel is protected by a random URL path and Argon2id login; use HTTPS via a trusted reverse proxy for Internet-facing deployments. This is an early functional release, not a claim of zero defects. See SECURITY.md and docs/INSTALL.md.
