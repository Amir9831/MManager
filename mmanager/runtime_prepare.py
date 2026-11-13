"""Repair MManager-managed listener properties immediately before every game-server start."""
import sys
from pathlib import Path

from . import core, store


def prepare(name):
    item = next((row for row in store.list_servers() if row.get("name") == name), None)
    if item is None:
        raise RuntimeError("No MManager server record matches this service instance")
    root = Path(item["directory"])
    ipv4 = bool(item.get("ipv4_enabled", 1))
    ipv6 = bool(item.get("ipv6_enabled", 0))
    if item["edition"] == "bedrock":
        core._configure_bedrock_properties(
            root / "server.properties", item["java_port"], item["version"],
            ipv4, ipv6, item.get("ipv6_port"),
        )
    else:
        core._configure_java_properties(root / "server.properties", item["java_port"], ipv4, ipv6)
        if item["edition"] == "crossplay":
            core._configure_geyser(
                root / "plugins" / "Geyser-Spigot" / "config.yml",
                item["bedrock_port"], item["java_port"], ipv4, ipv6,
            )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m mmanager.runtime_prepare SERVER_NAME")
    prepare(sys.argv[1])
