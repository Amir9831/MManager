# Security

- Web and API bind to loopback only; use SSH forwarding. Do not expose TCP 8765/8766.
- Admin password is Argon2id hashed. API bearer token is high entropy and stored root:mmanager mode 0640.
- Core runs as unprivileged mmanager. Only selected systemctl/journalctl operations for server template units are delegated.
- Minecraft processes run as mmanager with systemd filesystem protections.
- User-controlled IDs are regex-validated; subprocesses do not use a shell.
- Backup restore rejects path traversal and link/device entries, stops the server and creates a safety backup first.
- Server deletion is not exposed.
- Installer downloads GitHub archive over HTTPS but does not yet verify signed release provenance. Use only after reviewing source.
