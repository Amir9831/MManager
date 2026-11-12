# Roadmap

## Completed in 0.7.0
- [x] Java Vanilla/Paper and Bedrock Dedicated Server provisioning
- [x] Paper Geyser/Floodgate cross-play provisioning
- [x] Per-server file-backed logs and log rotation
- [x] Bedrock CDN browser User-Agent compatibility
- [x] Public panel explicit bind and configured port
- [x] Transactional installer with health checks and rollback
- [x] Narrow PolicyKit service authorization; no broad sudoers rule
- [x] Automatic firewall mutation removed; MManager leaves host/provider firewall unchanged
- [x] Backup import, download, deletion and guarded restore
- [x] Java/Cross-play player management and Bedrock role/allowlist controls
- [x] CI coverage for log readers and download request headers

## Known limitations / future work
- [ ] Fabric/Forge server installation and Modrinth mod lifecycle
- [ ] Multi-server selection and per-server API/UI routing
- [ ] Advanced Geyser configuration editor
- [ ] HTTPS termination inside MManager (public panel remains HTTP by user requirement)
- [ ] Native Bedrock ban list (not provided by BDS)
- [ ] Bedrock RCON (not provided by BDS)
- [ ] End-to-end VM tests for install, upgrade, rollback and game server startup
