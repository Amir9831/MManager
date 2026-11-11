# MManager

Modular Minecraft server manager for Ubuntu 22.04+.

Development build: CLI recovery menu, Core API, SQLite registry, port helper and purple dashboard. Minecraft runtime provisioning and production web authentication are not enabled yet. Do not expose the panel publicly.

## Development
`python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python -m mmanager`

Host paths: `/opt/mmanager` code, `/etc/mmanager` config, `/var/lib/mmanager` state/worlds/backups, `/var/log/mmanager` logs.
See `docs/` and `SECURITY.md`.
