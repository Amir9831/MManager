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
