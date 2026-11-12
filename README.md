# MManager

Minecraft server manager for Ubuntu 22.04 / 24.04 / 26.04.

## One-command install

```bash
curl -fsSL https://raw.githubusercontent.com/Amir9831/MManager/main/install.sh | sudo bash
```

Admin credentials: `/root/mmanager-admin-credentials.txt` (mode 0600). The installer prints the public panel URL with its random path and port. Use `sudo Mmanager` → **Web panel management** to change the path, administrator password, or port. The panel and browser API share one public TCP port; the core API remains loopback-only.

## مستندات فارسی

راهنمای نصب، امنیت، تنظیمات پنل و توضیح قابلیت‌ها: [docs/FA.md](docs/FA.md).

## Implemented

- Interactive CLI and in-CLI MManager updater.
- Argon2id administrator authentication and bearer-token API.
- Single-server setup for Java Vanilla/Paper, Bedrock Dedicated Server, and Paper + Geyser/Floodgate cross-play.
- Live release catalogs and bundled Java/Bedrock/Geyser templates.
- Editable `server.properties`, systemd lifecycle, and journal logs.
- Compressed backups, guarded restore, and safety backup before restore.
- RCON console and player list / Kick / Ban / Pardon for Java/Paper servers.
- Process-level CPU and RAM telemetry with robust `/proc` parsing and automatic panel refresh.
- World upload/switch management with ZIP validation and pre-change backups.
- Resource-pack configuration for Java/Cross-play and `.mcpack` installation for Bedrock.
- Guarded Java/Bedrock/Cross-play switching; incompatible worlds are archived rather than silently converted.
- External `.tar.gz`/`.tgz` backup import and one-click restore.
- Modrinth plugin search/install/remove for Paper and Cross-play; installation requires the server to be stopped.
- Minecraft server binary updates with pre-update backup and one-step rollback.

## Explicit limitations

- Automated game-port firewall configuration is not implemented. Open Java ports as TCP and Bedrock ports as UDP in UFW and the provider firewall.
- Standard Minecraft RCON and RCON-based player moderation are not available for Bedrock Dedicated Server. RCON is unencrypted and may listen on all interfaces; restrict its inbound TCP port yourself before enabling it.
- Plugin management is supported only on Paper-based servers (Paper and Cross-play), not Vanilla or Bedrock.
- Minecraft mods are not plugins. Fabric/Forge mod-loader installation is not yet implemented; the panel explains this instead of allowing incompatible mod JAR uploads.
- The panel should be exposed through HTTPS using a trusted reverse proxy for Internet-facing deployments. The random URL path is an additional layer, not a replacement for authentication.

MManager is an early functional release. Back up important worlds before upgrades or plugin changes and review [SECURITY.md](SECURITY.md) and [docs/INSTALL.md](docs/INSTALL.md).
