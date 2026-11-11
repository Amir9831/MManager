#!/usr/bin/env bash
set -Eeuo pipefail
umask 027
REPO="Amir9831/MManager"; URL="https://github.com/$REPO/archive/refs/heads/main.tar.gz"
say(){ printf '\n[MManager] %s\n' "$*"; }; fail(){ printf '\n[MManager][FATAL] %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail "Run: curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | sudo bash"
[[ -r /etc/os-release ]] || fail "Cannot detect OS"; . /etc/os-release
[[ "$ID" == ubuntu ]] || fail "Ubuntu required"
case "${VERSION_ID:-}" in 22.04|24.04|26.04) ;; *) fail "Supported Ubuntu: 22.04, 24.04, 26.04";; esac
command -v systemctl >/dev/null || fail "systemd required"
export DEBIAN_FRONTEND=noninteractive
say "Installing system dependencies"
apt-get update -y
if apt-cache show openjdk-21-jre-headless >/dev/null 2>&1; then
 apt-get install -y ca-certificates curl tar python3 python3-venv python3-pip openjdk-21-jre-headless sudo
else
 apt-get install -y ca-certificates curl tar wget gpg python3 python3-venv python3-pip sudo
 install -d -m 0755 /etc/apt/keyrings
 wget -qO- https://packages.adoptium.net/artifactory/api/gpg/key/public | gpg --dearmor -o /etc/apt/keyrings/adoptium.gpg
 echo "deb [signed-by=/etc/apt/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $VERSION_CODENAME main" >/etc/apt/sources.list.d/adoptium.list
 apt-get update -y; apt-get install -y temurin-21-jre
fi
id mmanager >/dev/null 2>&1 || useradd --system --home-dir /var/lib/mmanager --create-home --shell /usr/sbin/nologin mmanager
install -d -o root -g mmanager -m 0750 /etc/mmanager
install -d -o mmanager -g mmanager -m 0750 /var/lib/mmanager/servers /var/lib/mmanager/backups /var/log/mmanager
install -d -o root -g root -m 0755 /opt/mmanager/releases
TMP=$(mktemp -d); cleanup(){ rm -rf "$TMP"; }; trap cleanup EXIT
say "Downloading MManager from GitHub"
curl --fail --location --retry 3 --connect-timeout 15 "$URL" -o "$TMP/source.tar.gz"
mkdir "$TMP/src"; tar -xzf "$TMP/source.tar.gz" --strip-components=1 -C "$TMP/src"
[[ -f "$TMP/src/pyproject.toml" && -f "$TMP/src/mmanager/api.py" && -f "$TMP/src/systemd/mmanager-core.service" ]] || fail "Archive integrity sanity check failed"
RELEASE="/opt/mmanager/releases/$(date -u +%Y%m%d%H%M%S)"
mv "$TMP/src" "$RELEASE"
say "Building isolated Python environment"
python3 -m venv "$RELEASE/venv"
"$RELEASE/venv/bin/pip" install --upgrade pip
"$RELEASE/venv/bin/pip" install "$RELEASE"
"$RELEASE/venv/bin/python" -m compileall -q "$RELEASE/mmanager"
if [[ ! -s /etc/mmanager/auth.json ]]; then
 ADMIN_PASS=$(python3 -c 'import secrets;print(secrets.token_urlsafe(18))'); API_TOKEN=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))'); export ADMIN_PASS
 "$RELEASE/venv/bin/python" - <<'PY'
import json,os
from argon2 import PasswordHasher
with open("/etc/mmanager/auth.json","w") as f:json.dump({"password_hash":PasswordHasher().hash(os.environ["ADMIN_PASS"])},f)
PY
 printf '%s' "$API_TOKEN" >/etc/mmanager/api.token
 chown root:mmanager /etc/mmanager/auth.json /etc/mmanager/api.token; chmod 0640 /etc/mmanager/auth.json /etc/mmanager/api.token
 { echo "MManager administrator"; echo "Username: admin"; echo "Password: $ADMIN_PASS"; echo "Panel: http://127.0.0.1:8766"; echo "SSH: ssh -L 8766:127.0.0.1:8766 -L 8765:127.0.0.1:8765 USER@SERVER"; } >/root/mmanager-admin-credentials.txt
 chmod 0600 /root/mmanager-admin-credentials.txt; say "Admin password saved to /root/mmanager-admin-credentials.txt"
else say "Existing administrator credentials preserved"; fi
OLD=""; [[ -L /opt/mmanager/current ]] && OLD=$(readlink -f /opt/mmanager/current)
ln -sfn "$RELEASE" /opt/mmanager/current.next; mv -Tf /opt/mmanager/current.next /opt/mmanager/current
ln -sfn /opt/mmanager/current/venv/bin/Mmanager /usr/local/bin/Mmanager
cat >/etc/sudoers.d/mmanager <<'SUDO'
mmanager ALL=(root) NOPASSWD: /usr/bin/systemctl start mmanager-mc@*.service, /usr/bin/systemctl stop mmanager-mc@*.service, /usr/bin/systemctl restart mmanager-mc@*.service, /usr/bin/systemctl is-active --quiet mmanager-mc@*.service, /usr/bin/journalctl -u mmanager-mc@*.service -n * --no-pager -o cat
SUDO
chmod 0440 /etc/sudoers.d/mmanager; visudo -cf /etc/sudoers.d/mmanager >/dev/null
for unit in mmanager-core.service mmanager-web.service mmanager-mc@.service; do install -o root -g root -m 0644 "/opt/mmanager/current/systemd/$unit" "/etc/systemd/system/$unit"; done
chown -R mmanager:mmanager /var/lib/mmanager /var/log/mmanager
systemctl daemon-reload; systemctl enable mmanager-core.service mmanager-web.service
systemctl restart mmanager-core.service mmanager-web.service; sleep 2
if ! curl --fail --silent http://127.0.0.1:8765/api/health >/dev/null; then
 say "Core health check failed; rollback attempted"
 if [[ -n "$OLD" && -d "$OLD" ]]; then ln -sfn "$OLD" /opt/mmanager/current.rollback; mv -Tf /opt/mmanager/current.rollback /opt/mmanager/current; systemctl restart mmanager-core.service mmanager-web.service; fi
 fail "Core health check failed. Inspect journalctl -u mmanager-core"
fi
say "Installation completed"
echo "Panel: http://127.0.0.1:8766"; echo "Credentials: /root/mmanager-admin-credentials.txt"
echo "Remote access: ssh -L 8766:127.0.0.1:8766 -L 8765:127.0.0.1:8765 USER@SERVER"
echo "Panel/API bind to loopback only. Do not expose 8765/8766 publicly."
