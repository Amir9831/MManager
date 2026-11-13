import json

from mmanager import core, networking, runtime_prepare, store


def test_runtime_prepare_uses_readonly_config_not_database(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    server_dir = tmp_path / "servers" / "minecraft"
    server_dir.mkdir(parents=True)
    (data_root / "network").mkdir(parents=True)
    (data_root / "network" / "minecraft.json").write_text(json.dumps({
        "name": "minecraft", "directory": str(server_dir), "edition": "java",
        "version": "1.21.4", "java_port": 25565, "bedrock_port": None,
        "ipv6_port": None, "ipv4_enabled": True, "ipv6_enabled": False,
    }))
    monkeypatch.setattr(store, "DATA", data_root)
    monkeypatch.chdir(server_dir)
    applied = []
    bound = []
    monkeypatch.setattr(networking, "apply", lambda item, write_runtime=True: applied.append((item, write_runtime)))
    monkeypatch.setattr(core, "_configure_java_bind_address", lambda path, ipv4, ipv6: bound.append((path, ipv4, ipv6)))
    runtime_prepare.prepare("minecraft")
    assert applied and applied[0][1] is False
    assert bound == [(server_dir / "server.properties", True, False)]
