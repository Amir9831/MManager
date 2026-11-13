# MManager

Minecraft server manager for Ubuntu 22.04 / 24.04 / 26.04.

## One-command install

```bash
curl -fsSL https://raw.githubusercontent.com/Amir9831/MManager/main/install.sh | sudo bash
```

Admin credentials: `/root/mmanager-admin-credentials.txt` (mode 0600). On a fresh install, the installer prints the newly generated administrator password once, after all health checks pass, together with the public panel URL. Upgrades preserve existing credentials and never print the existing password. Use `sudo Mmanager` → **Web panel management** to change the path, administrator password, or port. CLI option 9 removes MManager itself after an explicit confirmation; Minecraft worlds and backups under `/var/lib/mmanager` are preserved. The panel and browser API share one public TCP port; the core API remains loopback-only.

## مستندات فارسی

راهنمای نصب، امنیت، تنظیمات پنل و توضیح قابلیت‌ها: [docs/FA.md](docs/FA.md).

## Implemented

- Interactive CLI and in-CLI MManager updater.
- Argon2id administrator authentication and bearer-token API.
- Single-server setup for Java Vanilla/Paper, Bedrock Dedicated Server, and Paper + Geyser/Floodgate cross-play.
- Live release catalogs, bundled Java/Bedrock/Geyser templates, and a validated Cross-play Geyser settings editor.
- Editable `server.properties`, systemd lifecycle, per-server file logs, and log rotation.
- Compressed backups, guarded restore, and safety backup before restore.
- Interactive game console: RCON for Java/Cross-play and a managed stdin FIFO for Bedrock Dedicated Server; supports commands and chat broadcasts.
- Three player lists (online, known offline, admins), Java OP levels 1–4, Bedrock Operator/Member/Visitor roles, Kick, and Java/Cross-play Ban/Pardon.
- Bedrock Dedicated Server has no native player ban list; its allowlist can restrict access only when enabled.
- Process-level CPU and RAM telemetry through same-user `/proc` access; no sudo elevation is needed.
- Per-server file-backed logs with bounded tail reads and log rotation; Java/Bedrock player activity uses those files. Systemd lifecycle authorization is restricted through PolicyKit and remains compatible with `NoNewPrivileges=true`.
- World upload/switch management with ZIP validation and pre-change backups.
- Resource-pack configuration for Java/Cross-play and `.mcpack` installation for Bedrock.
- Guarded Java/Bedrock/Cross-play switching; incompatible worlds are archived rather than silently converted.
- External `.tar.gz`/`.tgz` backup import and one-click restore.
- Modrinth plugin search/install/remove for Paper and Cross-play; installation requires the server to be stopped.
- Minecraft server binary updates with pre-update backup and one-step rollback.

## Explicit limitations

- Automated game-port firewall configuration is not implemented. Open Java Edition ports as TCP, Bedrock Dedicated Server ports as UDP, and Cross-play Geyser ports as both TCP and UDP in UFW and the provider firewall.
- RCON is unencrypted and may listen on all interfaces; restrict its inbound TCP port yourself before enabling it. Bedrock uses the local server stdin channel instead of RCON.
- Plugin management is supported only on Paper-based servers (Paper and Cross-play), not Vanilla or Bedrock.
- Minecraft mods are not plugins. Fabric/Forge mod-loader installation is not yet implemented; the panel explains this instead of allowing incompatible mod JAR uploads.
- The panel should be exposed through HTTPS using a trusted reverse proxy for Internet-facing deployments. The random URL path is an additional layer, not a replacement for authentication.

Version 0.7.0 keeps the public panel on HTTP as requested; use a trusted HTTPS reverse proxy when exposing it beyond a trusted network. Back up important worlds before upgrades or plugin changes and review [SECURITY.md](SECURITY.md) and [docs/INSTALL.md](docs/INSTALL.md).


## Bedrock networking (BDS 1.26.60+)

MManager configures Bedrock Dedicated Server 1.26.60 and newer to use NetherNet: `server-port` is the TCP signaling port, while gameplay uses UDP ports from `server-udp-ports` (`49152-49200`). Permit **both TCP on the configured `server-port` and UDP on `49152-49200`** in UFW and the provider firewall. The panel displays both transports for modern Bedrock servers. The UDP 7551 socket is LAN discovery, not the gameplay listener. Older BDS releases continue to use the legacy RakNet UDP listener and need only the configured UDP game port.
