"""Per-server IPv4/IPv6 packet policy for MManager-managed systemd units."""
import json
import os
import subprocess

from . import store


def _write_runtime_config(item, name, ipv4, ipv6):
    if not item.get("directory"):
        return
    directory = store.DATA / "network"
    directory.mkdir(parents=True, exist_ok=True)
    data = {
        "name": name,
        "directory": str(item["directory"]),
        "edition": item.get("edition", "java"),
        "version": item.get("version", ""),
        "java_port": item.get("java_port"),
        "bedrock_port": item.get("bedrock_port"),
        "ipv6_port": item.get("ipv6_port"),
        "ipv4_enabled": ipv4,
        "ipv6_enabled": ipv6,
    }
    path = directory / (name + ".json")
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, separators=(",", ":")) + "\n")
    os.chmod(temporary, 0o640)
    os.replace(temporary, path)


def apply(item, write_runtime=True):
    name = str(item.get("name", ""))
    if not name or not name.replace("-", "").replace("_", "").isalnum():
        raise RuntimeError("Invalid Minecraft server unit name")
    ipv4 = bool(item.get("ipv4_enabled", 1))
    ipv6 = bool(item.get("ipv6_enabled", 0))
    if not ipv4 and not ipv6:
        raise RuntimeError("At least one IP family must remain enabled")
    denied = []
    if not ipv4:
        denied.append("0.0.0.0/0")
    if not ipv6:
        denied.append("::/0")
    if write_runtime:
        _write_runtime_config(item, name, ipv4, ipv6)
    assignment = "IPAddressDeny=" + " ".join(denied)
    unit = f"mmanager-mc@{name}.service"
    result = subprocess.run(
        ["/usr/bin/systemctl", "set-property", "--runtime", unit, assignment],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        detail = (result.stderr.strip() or result.stdout.strip())[:300]
        raise RuntimeError("Cannot apply per-server IP policy: " + detail)
    return {"ipv4_enabled": ipv4, "ipv6_enabled": ipv6}


def restore():
    failures = []
    for item in store.list_servers():
        try:
            apply(item)
        except Exception as exc:
            failures.append(f"{item.get('name', '?')}: {exc}")
    if failures:
        raise RuntimeError("Network policy restore failed: " + "; ".join(failures))


if __name__ == "__main__":
    restore()
