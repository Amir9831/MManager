# Architecture

`Mmanager` is the recovery CLI and calls systemd directly, so it remains usable when Core/Web are down. Core owns registry and server lifecycle. Web consumes Core API. Server adapters: Java, Bedrock, Crossplay (Java plus Geyser/Floodgate).

Paths: `/opt/mmanager` code, `/etc/mmanager` config/secrets, `/var/lib/mmanager` DB/worlds/backups, `/var/log/mmanager` logs.

Port availability is protocol-specific (TCP != UDP). Current helper probes a port; a production allocator must reserve transactionally in the DB and bind-check immediately before commit. Updates must stage, verify signature/checksum, preserve state/config, activate atomically, health-check and rollback.
