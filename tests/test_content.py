from pathlib import Path
import zipfile
from mmanager import content, core, settings, store


def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    monkeypatch.setattr(store, "DB", tmp_path / "data" / "test.sqlite3")
    monkeypatch.setattr(settings, "SERVERS", tmp_path / "servers")
    monkeypatch.setattr(settings, "BACKUPS", tmp_path / "backups")
    monkeypatch.setattr(core, "choose_port", lambda preferred, protocol, reserved: preferred)
    monkeypatch.setattr(core, "_vanilla", lambda v: {"url": "https://example.invalid/server.jar", "checksum": None, "algorithm": "sha1"})
    monkeypatch.setattr(core, "_paper", lambda v: {"url": "https://example.invalid/paper.jar", "checksum": None, "algorithm": "sha256"})
    monkeypatch.setattr(core, "_download", lambda url, dest, *args: Path(dest).write_bytes(b"x" * 2048))
    monkeypatch.setattr(core, "_active", lambda item: False)
    monkeypatch.setattr(core, "_systemctl", lambda action, item: None)


def test_world_upload_and_activation(monkeypatch, tmp_path):
    import io
    setup(monkeypatch, tmp_path)
    item = core.create_server("minecraft", "java", "1.21.4", "vanilla", True)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("MyWorld/level.dat", b"world")
        z.writestr("MyWorld/region/r.0.0.mca", b"region")
    archive.seek(0)
    result = content.upload_world(item["id"], "ImportedWorld", archive, "world.zip")
    assert result["uploaded"] is True
    worlds = content.list_worlds(item["id"])
    assert any(x["name"] == "ImportedWorld" for x in worlds["items"])
    content.activate_world(item["id"], "ImportedWorld")
    assert core.server_settings(item["id"])["settings"]["level-name"] == "ImportedWorld"


def test_world_upload_rejects_zip_slip(monkeypatch, tmp_path):
    import io
    import pytest
    setup(monkeypatch, tmp_path)
    item = core.create_server("minecraft", "java", "1.21.4", "vanilla", True)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../escape/level.dat", b"bad")
    archive.seek(0)
    with pytest.raises(core.ManagerError, match="Unsafe archive"):
        content.upload_world(item["id"], "bad", archive, "bad.zip")


def test_java_to_crossplay_switch_preserves_world(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    item = core.create_server("minecraft", "java", "1.21.4", "vanilla", True)
    world = Path(item["directory"]) / "world"
    world.mkdir()
    (world / "level.dat").write_bytes(b"world")
    result = core.switch_server(item["id"], "crossplay", "paper", "1.21.4")
    updated = store.get_server(item["id"])
    assert result["switched"] is True
    assert updated["edition"] == "crossplay"
    assert updated["software"] == "paper"
    assert (Path(updated["directory"]) / "world" / "level.dat").read_bytes() == b"world"
    assert (Path(updated["directory"]) / "plugins" / "Geyser-Spigot.jar").exists()
    assert (Path(updated["directory"]) / "plugins" / "floodgate-spigot.jar").exists()


def test_java_to_bedrock_switch_archives_world_instead_of_converting(monkeypatch, tmp_path):
    import pytest
    setup(monkeypatch, tmp_path)
    item = core.create_server("minecraft", "java", "1.21.4", "vanilla", True)
    old_root = Path(item["directory"])
    (old_root / "world").mkdir()
    (old_root / "world" / "level.dat").write_bytes(b"java-world")
    monkeypatch.setattr(core, "_bedrock", lambda v: {"url": "https://example.invalid/bds.zip", "checksum": None, "algorithm": "sha256"})
    def download(url, dest, *args):
        with zipfile.ZipFile(dest, "w") as z:
            z.writestr("bedrock_server", b"fake bds binary")
    monkeypatch.setattr(core, "_download", download)
    with pytest.raises(core.ManagerError, match="does not convert worlds"):
        core.switch_server(item["id"], "bedrock", "bedrock", "1.26.63")
    result = core.switch_server(item["id"], "bedrock", "bedrock", "1.26.63", True)
    updated = store.get_server(item["id"])
    assert result["world_archived"] is True
    assert updated["edition"] == "bedrock"
    assert (old_root / "bedrock_server").exists()
    archived = list(old_root.parent.glob("minecraft.archived-*"))
    assert archived and (archived[0] / "world" / "level.dat").read_bytes() == b"java-world"
