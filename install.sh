#!/usr/bin/env bash
set -Eeuo pipefail
umask 027
REPO="Amir9831/MManager"
CURRENT="/opt/mmanager/current"
say(){ printf '\n[MManager] %s\n' "$*"; }
fail(){
 printf '\n[MManager][FATAL] %s\n' "$*" >&2
 if [[ "${ROLLBACK_ACTIVE:-0}" == "1" ]]; then
  on_error 1 "${BASH_LINENO[0]:-0}"
 else
  exit 1
 fi
}

[[ $EUID -eq 0 ]] || fail "Run: curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | sudo bash"
[[ -r /etc/os-release ]] || fail "Cannot detect OS"
. /etc/os-release
[[ "$ID" == ubuntu ]] || fail "Ubuntu required"
case "$VERSION_ID" in 22.04|24.04|26.04) ;; *) fail "Supported Ubuntu: 22.04, 24.04, 26.04";; esac
[[ "$(ps -p 1 -o comm= | tr -d ' ')" == "systemd" ]] || fail "systemd must be running as PID 1"
command -v flock >/dev/null 2>&1 || fail "flock is required (install util-linux)"

install -d -m 0755 /run/lock
exec 9>/run/lock/mmanager-install.lock
flock -n 9 || fail "Another MManager installation or upgrade is already running"

export DEBIAN_FRONTEND=noninteractive
say "Installing system dependencies"
apt-get update -y
BDS_RUNTIME_PKGS=(libstdc++6 libatomic1)
for pair in "libcurl4 libcurl4t64" "libssl3 libssl3t64"; do
 for candidate in $pair; do
  if apt-cache show "$candidate" >/dev/null 2>&1; then BDS_RUNTIME_PKGS+=("$candidate"); break; fi
 done
done
if apt-cache show openjdk-21-jre-headless >/dev/null 2>&1; then
 apt-get install -y ca-certificates curl tar python3 python3-venv python3-pip openjdk-21-jre-headless sudo policykit-1 util-linux logrotate git "${BDS_RUNTIME_PKGS[@]}"
else
 apt-get install -y ca-certificates curl tar wget gpg python3 python3-venv python3-pip sudo policykit-1 util-linux logrotate git "${BDS_RUNTIME_PKGS[@]}"
 install -d -m 0755 /etc/apt/keyrings
 wget -qO- https://packages.adoptium.net/artifactory/api/gpg/key/public | gpg --dearmor --yes -o /etc/apt/keyrings/adoptium.gpg
 echo "deb [signed-by=/etc/apt/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $VERSION_CODENAME main" >/etc/apt/sources.list.d/adoptium.list
 apt-get update -y
 apt-get install -y temurin-21-jre
fi

TMP=$(mktemp -d)
RELEASE=""
APP=""
OLD=""
ROLLBACK_ACTIVE=0
SNAPSHOT="$TMP/snapshot"
ABSENT="$TMP/absent.list"
: >"$ABSENT"

snapshot_file(){
 local path="$1" rel
 rel=$(printf '%s' "$path" | sed 's#^/##')
 if [[ -e "$path" || -L "$path" ]]; then
  mkdir -p "$SNAPSHOT/$(dirname "$rel")"
  cp -a "$path" "$SNAPSHOT/$rel"
 else
  printf '%s\n' "$path" >>"$ABSENT"
 fi
}
restore_snapshot(){
 if [[ -f "$ABSENT" ]]; then
  while IFS= read -r path; do [[ -n "$path" ]] && rm -f "$path"; done <"$ABSENT"
 fi
 [[ ! -d "$SNAPSHOT" ]] || cp -a "$SNAPSHOT/." /
}
on_error(){
 local rc="$1" line="$2"
 trap - ERR
 if [[ "$ROLLBACK_ACTIVE" == "1" ]]; then
  say "Installation failed at line $line; restoring the previous release and service configuration"
  if [[ -n "$OLD" && -d "$OLD" ]]; then
   ln -sfn "$OLD" "$CURRENT.rollback" || true
   mv -Tf "$CURRENT.rollback" "$CURRENT" || true
  else
   rm -f "$CURRENT" "$CURRENT.rollback" /usr/local/bin/Mmanager
  fi
  if [[ "$OLD_JOURNAL_MEMBER" == "1" ]]; then usermod -aG systemd-journal mmanager 2>/dev/null || true; else gpasswd -d mmanager systemd-journal >/dev/null 2>&1 || true; fi
  restore_snapshot || true
  systemctl daemon-reload || true
  if [[ -n "$OLD" && -d "$OLD" ]]; then
   systemctl restart mmanager-core.service mmanager-web.service || true
   while read -r unit; do
    [[ "$unit" =~ ^mmanager-mc@[A-Za-z0-9_-]+\.service$ ]] && systemctl restart "$unit" || true
   done <"$TMP/active-mc-units"
  else
   systemctl disable --now mmanager-core.service mmanager-web.service || true
  fi
  ROLLBACK_ACTIVE=0
 fi
 exit "$rc"
}
cleanup(){
 if [[ -n "$RELEASE" && -d "$RELEASE" ]]; then
  local active
  active=$(readlink -f "$CURRENT" 2>/dev/null || true)
  [[ "$active" == "$APP" ]] || rm -rf "$RELEASE"
 fi
 rm -rf "$TMP"
}
trap cleanup EXIT
trap 'on_error "$?" "$LINENO"' ERR

id mmanager >/dev/null 2>&1 || useradd --system --home-dir /var/lib/mmanager --create-home --shell /usr/sbin/nologin mmanager
install -d -o root -g mmanager -m 0750 /etc/mmanager
chown root:mmanager /etc/mmanager
chmod 0750 /etc/mmanager
install -d -o mmanager -g mmanager -m 0750 /var/lib/mmanager /var/lib/mmanager/servers /var/lib/mmanager/backups /var/log/mmanager /var/log/mmanager/servers
chown -R mmanager:mmanager /var/lib/mmanager /var/log/mmanager
find /var/lib/mmanager /var/log/mmanager -type d -exec chmod 0750 {} +
find /var/lib/mmanager/servers /var/lib/mmanager/backups -type f -exec chmod u+rw,go-rwx {} +
find /var/lib/mmanager/servers -type f \( -name run.sh -o -name bedrock_server \) -exec chmod u+x {} +

say "Resolving the MManager source revision"
curl --fail --location --retry 3 --connect-timeout 15 "https://api.github.com/repos/$REPO/commits/main" -o "$TMP/commit.json"
COMMIT=$(python3 -c 'import json,re,sys; s=json.load(open(sys.argv[1])).get("sha",""); print(s if re.fullmatch(r"[0-9a-f]{40}",s) else "")' "$TMP/commit.json")
[[ -n "$COMMIT" ]] || fail "GitHub did not return a valid commit SHA"
git init -q "$TMP/repo"
git -C "$TMP/repo" remote add origin "https://github.com/$REPO.git"
git -C "$TMP/repo" fetch --quiet --depth=1 origin "$COMMIT"
FETCHED_COMMIT=$(git -C "$TMP/repo" rev-parse FETCH_HEAD)
[[ "$FETCHED_COMMIT" == "$COMMIT" ]] || fail "Fetched Git commit does not match the requested SHA"
mkdir "$TMP/src"
git -C "$TMP/repo" archive "$COMMIT" | tar -x -C "$TMP/src"
[[ -f "$TMP/src/pyproject.toml" && -f "$TMP/src/mmanager/api.py" && -f "$TMP/src/systemd/mmanager-core.service" ]] || fail "Archive integrity sanity check failed"

install -d -o root -g root -m 0755 /opt/mmanager /opt/mmanager/releases
chown root:root /opt/mmanager /opt/mmanager/releases
chmod 0755 /opt/mmanager /opt/mmanager/releases
RELEASE=$(mktemp -d "/opt/mmanager/releases/$(date -u +%Y%m%d%H%M%S)-XXXXXXXX")
APP="$RELEASE/source"
mv "$TMP/src" "$APP"
printf '%s\n' "$COMMIT" >"$APP/.mmanager-commit"

say "Building isolated Python environment"
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install --upgrade pip
"$APP/venv/bin/pip" install "$APP"
"$APP/venv/bin/python" -m compileall -q "$APP/mmanager"
chgrp -R mmanager "$RELEASE"
chmod -R g+rX "$RELEASE"

ADMIN_PASS=""
if [[ ! -s /etc/mmanager/auth.json ]]; then
 ADMIN_PASS=$(python3 -c 'import secrets;print(secrets.token_urlsafe(18))')
 export ADMIN_PASS
 "$APP/venv/bin/python" - <<'PY'
import json,os,tempfile
from pathlib import Path
from argon2 import PasswordHasher
target=Path("/etc/mmanager/auth.json")
fd,tmp=tempfile.mkstemp(prefix=".auth.",dir=str(target.parent))
try:
    with os.fdopen(fd,"w") as f:
        json.dump({"password_hash":PasswordHasher().hash(os.environ["ADMIN_PASS"])},f)
        f.flush(); os.fsync(f.fileno())
    os.chmod(tmp,0o640)
    os.replace(tmp,target)
finally:
    if os.path.exists(tmp): os.unlink(tmp)
PY
fi
if [[ ! -s /etc/mmanager/api.token ]]; then
 API_TOKEN=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
 API_TMP=$(mktemp /etc/mmanager/.api-token.XXXXXX)
 printf '%s' "$API_TOKEN" >"$API_TMP"
 chown root:mmanager "$API_TMP"
 chmod 0640 "$API_TMP"
 mv -f "$API_TMP" /etc/mmanager/api.token
fi
chown root:mmanager /etc/mmanager/auth.json /etc/mmanager/api.token
chmod 0640 /etc/mmanager/auth.json /etc/mmanager/api.token
if [[ -n "$ADMIN_PASS" ]]; then
 {
  echo "MManager administrator"
  echo "Password: $ADMIN_PASS"
  echo "Panel: http://127.0.0.1:8766"
 } >/root/mmanager-admin-credentials.txt
 chown root:root /root/mmanager-admin-credentials.txt
 chmod 0600 /root/mmanager-admin-credentials.txt
 say "A new administrator password was saved to /root/mmanager-admin-credentials.txt (not printed to stdout)"
else
 say "Existing administrator credentials preserved"
fi

# Keep the existing public HTTP panel URL, path and port behavior unchanged.
if [[ ! -s /etc/mmanager/web.json ]]; then
 PANEL_PATH=$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')
 printf '{"path":"%s","port":8766}\n' "$PANEL_PATH" >/etc/mmanager/web.json
fi
chown root:mmanager /etc/mmanager/web.json
chmod 0640 /etc/mmanager/web.json
PANEL_PATH=$(python3 -c 'import json;print(json.load(open("/etc/mmanager/web.json"))["path"])')
PANEL_PORT=$(python3 -c 'import json;print(json.load(open("/etc/mmanager/web.json"))["port"])')
[[ "$PANEL_PATH" =~ ^[A-Za-z0-9_-]{24,128}$ ]] || fail "Invalid panel path in /etc/mmanager/web.json"
[[ "$PANEL_PORT" =~ ^[0-9]+$ ]] && (( PANEL_PORT >= 1024 && PANEL_PORT <= 65535 )) || fail "Invalid panel port in /etc/mmanager/web.json"
printf 'UVICORN_PORT=%s\n' "$PANEL_PORT" >/etc/mmanager/web.env
chown root:mmanager /etc/mmanager/web.env
chmod 0640 /etc/mmanager/web.env

OLD=""
[[ -L "$CURRENT" ]] && OLD=$(readlink -f "$CURRENT" || true)
[[ -z "$OLD" || -d "$OLD" ]] || fail "The current MManager release link is broken"
OLD_JOURNAL_MEMBER=0
id -nG mmanager 2>/dev/null | tr ' ' '\n' | grep -qx systemd-journal && OLD_JOURNAL_MEMBER=1 || true
for path in /etc/systemd/system/mmanager-core.service /etc/systemd/system/mmanager-web.service /etc/systemd/system/mmanager-mc@.service /etc/polkit-1/rules.d/50-mmanager.rules /etc/sudoers.d/mmanager /etc/logrotate.d/mmanager; do
 snapshot_file "$path"
done
: >"$TMP/active-mc-units"
systemctl list-units --type=service --state=running --no-legend 'mmanager-mc@*.service' 2>/dev/null | awk '{print $1}' | grep -E '^mmanager-mc@[A-Za-z0-9_-]+\.service$' >"$TMP/active-mc-units" || true

ROLLBACK_ACTIVE=1
ln -sfn "$APP" "$CURRENT.next"
mv -Tf "$CURRENT.next" "$CURRENT"
ln -sfn "$CURRENT/venv/bin/Mmanager" /usr/local/bin/Mmanager

install -d -m 0755 /etc/polkit-1/rules.d
cat >/etc/polkit-1/rules.d/50-mmanager.rules <<'POLKIT'
polkit.addRule(function(action, subject) {
    if (subject.user == "mmanager" &&
        action.id == "org.freedesktop.systemd1.manage-units" &&
        /^mmanager-mc@[A-Za-z0-9][A-Za-z0-9_-]{1,31}\.service$/.test(action.lookup("unit") || "") &&
        ["start", "stop", "restart"].indexOf(action.lookup("verb")) >= 0) {
        return polkit.Result.YES;
    }
});
POLKIT
chmod 0644 /etc/polkit-1/rules.d/50-mmanager.rules
rm -f /etc/sudoers.d/mmanager
for unit in mmanager-core.service mmanager-web.service mmanager-mc@.service; do
 install -o root -g root -m 0644 "$CURRENT/systemd/$unit" "/etc/systemd/system/$unit"
done
cat >/etc/logrotate.d/mmanager <<'LOGROTATE'
/var/log/mmanager/servers/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    create 0640 mmanager mmanager
}
LOGROTATE
chmod 0644 /etc/logrotate.d/mmanager

if getent group systemd-journal >/dev/null 2>&1; then
 gpasswd -d mmanager systemd-journal >/dev/null 2>&1 || true
fi
systemctl daemon-reload
systemctl enable mmanager-core.service mmanager-web.service
systemctl restart mmanager-core.service mmanager-web.service

while IFS= read -r unit; do
 [[ "$unit" =~ ^mmanager-mc@[A-Za-z0-9_-]+\.service$ ]] || continue
 systemctl restart "$unit"
done <"$TMP/active-mc-units"

CORE_OK=0
WEB_OK=0
for attempt in {1..30}; do
 if curl --fail --silent --max-time 2 http://127.0.0.1:8765/api/health >/dev/null; then CORE_OK=1; fi
 if curl --fail --silent --max-time 2 "http://127.0.0.1:$PANEL_PORT/$PANEL_PATH/api/health" >/dev/null; then WEB_OK=1; fi
 [[ "$CORE_OK" == 1 && "$WEB_OK" == 1 ]] && break
 sleep 1
done
[[ "$CORE_OK" == 1 ]] || fail "Core health check failed"
[[ "$WEB_OK" == 1 ]] || fail "Web panel health check failed"
systemctl is-active --quiet mmanager-core.service
systemctl is-active --quiet mmanager-web.service
ROLLBACK_ACTIVE=0
say "Installation completed successfully"

CURRENT_RELEASE=$(readlink -f "$CURRENT")
kept=0
while IFS= read -r candidate; do
 [[ -n "$candidate" ]] || continue
 [[ "$(readlink -f "$candidate/source" 2>/dev/null || true)" == "$CURRENT_RELEASE" ]] && continue
 kept=$((kept+1))
 if (( kept > 2 )); then rm -rf "$candidate"; fi
done < <(find /opt/mmanager/releases -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -rn | awk '{print $2}')

PUBLIC_IP=$(curl -4fsS --connect-timeout 5 https://api.ipify.org || true)
[[ -n "$PUBLIC_IP" ]] || PUBLIC_IP="<PUBLIC_IP>"
PANEL_URL="http://$PUBLIC_IP:$PANEL_PORT/$PANEL_PATH/"
if [[ -f /root/mmanager-admin-credentials.txt ]]; then
 python3 - "$PANEL_URL" <<'PY'
import pathlib,sys
p=pathlib.Path("/root/mmanager-admin-credentials.txt")
lines=[x for x in p.read_text().splitlines() if not x.startswith("Panel:")]
lines.append("Panel: "+sys.argv[1])
p.write_text("\n".join(lines)+"\n")
p.chmod(0o600)
PY
fi
echo "Panel: $PANEL_URL"
if [[ -f /root/mmanager-admin-credentials.txt ]]; then
 echo "Credentials file: /root/mmanager-admin-credentials.txt (password is never printed)"
else
 echo "Existing administrator credentials preserved; no password was printed."
fi
echo "Manage panel path, password and port from the MManager CLI (option 7)."
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then ufw allow "$PANEL_PORT/tcp" || say "Could not update UFW; open TCP $PANEL_PORT manually"; fi
echo "Allow TCP port $PANEL_PORT in your VPS/cloud firewall if applicable."
