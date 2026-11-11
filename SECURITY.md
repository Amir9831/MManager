# Security

- Panel/API bind to loopback only; use SSH forwarding. Do not expose ports 8765/8766.
- Password hashes use Argon2id. A high-entropy bearer token is stored root:mmanager mode 0640.
- Core and game servers run as unprivileged mmanager. A narrow sudoers rule delegates only named service-template operations.
- IDs are strictly validated; subprocesses use argument arrays, never a shell.
- Backup pauses an active server, excludes symlinks, and resumes it. Restore validates archive paths and member types, stops the server and creates a safety backup first.
- No destructive server deletion endpoint is provided.
- GitHub archive is fetched over HTTPS; signed release provenance is not yet verified.
- Configure firewall rules for the game ports shown in the panel/registry. Firewall automation is not yet included.
