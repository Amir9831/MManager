"""Repair MManager-managed listener properties immediately before every game-server start."""
import json
import sys
from pathlib import Path

from . import core, store


def prepare(name):
    config_path = store.DATA / "network" / (name + ".json")
    try:
        item = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Cannot read MManager network runtime config: " + str(exc))
    if item.get("name") != name:
        raise RuntimeError("MManager network runtime config does not match this service instance")
    root = Path(item["directory"])
    if root.resolve() != Path.cwd().resolve():
        raise RuntimeError("MManager runtime config points to a different server directory")
    if item.get("edition") not in {"java", "bedrock", "crossplay"}:
        raise RuntimeError("Invalid server edition in MManager runtime config")
    ipv4 = bool(item.get("ipv4_enabled", 1))
    ipv6 = bool(item.get("ipv6_enabled", 0))
    if item["edition"] == "bedrock":
        core._configure_bedrock_properties(
            root / "server.properties", item["java_port"], item["version"],
            ipv4, ipv6, item.get("ipv6_port"),
        )
    else:
        core._configure_java_bind_address(root / "server.properties", ipv4, ipv6)
        if item["edition"] == "crossplay":
            core._configure_geyser_bind_address(
                root / "plugins" / "Geyser-Spigot" / "config.yml", ipv4, ipv6,
            )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m mmanager.runtime_prepare SERVER_NAME")
    prepare(sys.argv[1])
