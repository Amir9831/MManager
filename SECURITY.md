# Security

- The public web panel and browser API are served on one configurable TCP port, behind a high-entropy random URL path. Requests outside that path receive 404.
- The administrator password is verified using Argon2id and login is rate-limited. API routes require the bearer token; health and static assets are reachable only beneath the secret path.
- The separate core API remains bound to loopback. Do not expose TCP 8765.
- The random path is an additional access barrier, not a substitute for authentication. Use a strong administrator password and HTTPS via a trusted reverse proxy when exposing the panel over the Internet; the built-in listener is HTTP.
- Core and game servers run as unprivileged mmanager. A narrow sudoers rule delegates only named service-template operations.
- IDs are strictly validated; subprocesses use argument arrays, never a shell.
- Backup pauses an active server, excludes symlinks, and resumes it. Restore validates archive paths and member types, stops the server and creates a safety backup first.
- No destructive server deletion endpoint is provided.
- GitHub archive is fetched over HTTPS; signed release provenance is not yet verified.
- Configure firewall rules for the panel port and game ports shown in the panel/registry. Firewall automation is not yet included.
