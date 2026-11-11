import pytest
from mmanager import core, store

def setup_isolated(monkeypatch, tmp_path):
    state = tmp_path / "state"
    monkeypatch.setattr(store, "DATA", state)
    monkeypatch.setattr(store, "DB", state / "test.sqlite3")
    monkeypatch.setattr(core, "SERVERS", tmp_path / "servers")
    monkeypatch.setattr(core, "choose_port",
        lambda preferred, protocol, reserved: preferred if preferred not in reserved else preferred + 1)

def test_create_registers_crossplay_ports_and_directory(monkeypatch, tmp_path):
    setup_isolated(monkeypatch, tmp_path)
    item = core.create_server("survival_1", "crossplay", "1.21.4")
    assert item["java_port"] == 25565
    assert item["bedrock_port"] == 19132
    assert (tmp_path / "servers" / "survival_1").is_dir()
    assert store.list_servers()[0]["id"] == item["id"]

def test_duplicate_server_name_is_rejected(monkeypatch, tmp_path):
    setup_isolated(monkeypatch, tmp_path)
    core.create_server("survival_1", "java", "1.21.4")
    with pytest.raises(core.ManagerError, match="GM-104"):
        core.create_server("survival_1", "java", "1.21.4")

def test_delete_requires_confirmation_and_retains_world_data(monkeypatch, tmp_path):
    setup_isolated(monkeypatch, tmp_path)
    item = core.create_server("survival_1", "java", "1.21.4")
    with pytest.raises(core.ManagerError, match="GM-105"):
        core.delete_server(item["id"])
    result = core.delete_server(item["id"], confirm=True)
    assert result["data_retained"] is True
    assert (tmp_path / "servers" / "survival_1").is_dir()
    assert store.list_servers() == []
