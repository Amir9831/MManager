#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "[MManager][ERROR] Installation failed at line $LINENO. No game data was deleted." >&2' ERR
fail(){ echo "[MManager][ERROR] $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail "Run: sudo bash scripts/install.sh"
[[ -r /etc/os-release ]] || fail "Cannot identify operating system"
. /etc/os-release
[[ "$ID" == ubuntu ]] || fail "Ubuntu 22.04+ required"
python3 - <<'PY' || exit 1
import sys
if sys.version_info < (3,10): raise SystemExit('[GM-003] Python 3.10+ required')
PY
command -v systemctl >/dev/null || fail "systemd is required"
echo '[MManager] Preflight passed. Installer is non-mutating in this development build.'
echo '[MManager] Full service installation waits for tested authentication, runtime isolation and rollback.'
