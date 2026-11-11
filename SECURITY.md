# Security

Development build only. API binds to loopback. Do not expose publicly until authentication, CSRF, rate limiting, audit logging and secure sessions are implemented. Game processes must run as an unprivileged OS user. Never overwrite `/etc/mmanager` or `/var/lib/mmanager` during updates. Destructive actions require confirmation and safe path validation. Auto-repair must not delete worlds/backups.
