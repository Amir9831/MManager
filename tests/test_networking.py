import subprocess

from mmanager import networking


def test_ipv6_disabled_applies_service_scoped_deny(monkeypatch):
    seen = []
    def fake_run(command, **kwargs):
        seen.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(networking.subprocess, "run", fake_run)
    result = networking.apply({"name": "minecraft", "ipv4_enabled": 1, "ipv6_enabled": 0})
    assert result == {"ipv4_enabled": True, "ipv6_enabled": False}
    assert seen[0][0] == [
        "/usr/bin/systemctl", "set-property", "--runtime",
        "mmanager-mc@minecraft.service", "IPAddressDeny=::/0",
    ]


def test_ipv4_disabled_applies_only_ipv4_deny(monkeypatch):
    seen = []
    def fake_run(command, **kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(networking.subprocess, "run", fake_run)
    networking.apply({"name": "minecraft", "ipv4_enabled": 0, "ipv6_enabled": 1})
    assert seen[0][-1] == "IPAddressDeny=0.0.0.0/0"


def test_dual_stack_clears_service_deny(monkeypatch):
    seen = []
    def fake_run(command, **kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(networking.subprocess, "run", fake_run)
    networking.apply({"name": "minecraft", "ipv4_enabled": 1, "ipv6_enabled": 1})
    assert seen[0][-1] == "IPAddressDeny="


def test_invalid_unit_name_and_both_families_disabled_are_rejected(monkeypatch):
    import pytest
    with pytest.raises(RuntimeError, match="Invalid Minecraft server unit name"):
        networking.apply({"name": "../bad", "ipv4_enabled": 1, "ipv6_enabled": 0})
    with pytest.raises(RuntimeError, match="At least one IP family"):
        networking.apply({"name": "minecraft", "ipv4_enabled": 0, "ipv6_enabled": 0})


def test_apply_writes_read_only_runtime_config(monkeypatch, tmp_path):
    import json
    data_root = tmp_path / "data"
    server_dir = tmp_path / "servers" / "minecraft"
    server_dir.mkdir(parents=True)
    monkeypatch.setattr(networking.store, "DATA", data_root)
    monkeypatch.setattr(
        networking.subprocess, "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "", ""),
    )
    item = {
        "name": "minecraft", "directory": str(server_dir), "edition": "bedrock",
        "version": "1.26.33", "java_port": 19132, "ipv6_port": 19133,
        "ipv4_enabled": 1, "ipv6_enabled": 0,
    }
    networking.apply(item)
    config = json.loads((data_root / "network" / "minecraft.json").read_text())
    assert config["ipv4_enabled"] is True
    assert config["ipv6_enabled"] is False
    assert config["ipv6_port"] == 19133
