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
    monkeypatch.setattr(core.networking, "apply", lambda item, write_runtime=True: None)


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


def test_java_resource_pack_configuration(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    item = core.create_server("minecraft", "java", "1.21.4", "vanilla", True)
    content.configure_java_resource_pack(item["id"], "https://cdn.example.test/pack.zip", "a" * 40, True)
    info = content.resource_pack_info(item["id"])
    assert info["url"] == "https://cdn.example.test/pack.zip"
    assert info["sha1"] == "a" * 40
    assert info["required"] is True


def test_import_backup_registers_only_valid_manager_archives(monkeypatch, tmp_path):
    import io
    import tarfile
    import pytest
    setup(monkeypatch, tmp_path)
    item = core.create_server("minecraft", "java", "1.21.4", "vanilla", True)
    valid = io.BytesIO()
    with tarfile.open(fileobj=valid, mode="w:gz") as archive:
        for name, data in (("server.properties", b"level-name=world\n"), ("server.jar", b"server-binary")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    valid.seek(0)
    imported = core.import_backup(item["id"], valid, "old-backup.tar.gz")
    assert imported["imported"] is True
    assert any(row["id"] == imported["id"] for row in core.list_backups(item["id"]))
    invalid = io.BytesIO(b"not a tar archive" * 20)
    with pytest.raises((core.ManagerError, tarfile.TarError)):
        core.import_backup(item["id"], invalid, "bad.tar.gz")


def test_bedrock_mcpack_install_and_remove(monkeypatch, tmp_path):
    import io
    import json
    import uuid
    setup(monkeypatch, tmp_path)
    monkeypatch.setattr(core, "_bedrock", lambda v: {"url": "https://example.invalid/bds.zip", "checksum": None, "algorithm": "sha256"})
    def download(url, dest, *args):
        with zipfile.ZipFile(dest, "w") as z:
            z.writestr("bedrock_server", b"fake bds binary")
    monkeypatch.setattr(core, "_download", download)
    item = core.create_server("minecraft", "bedrock", "1.26.63", "bedrock", True)
    world = Path(item["directory"]) / "worlds" / "Bedrock level"
    world.mkdir(parents=True)
    (world / "level.dat").write_bytes(b"world")
    pack_id = str(uuid.uuid4())
    pack = io.BytesIO()
    manifest = {"format_version": 2, "header": {"name": "Test Pack", "description": "test", "uuid": pack_id, "version": [1, 0, 0]}, "modules": []}
    with zipfile.ZipFile(pack, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        z.writestr("textures/test.txt", "resource")
    pack.seek(0)
    result = content.install_bedrock_resource_pack(item["id"], pack, "test.mcpack", True)
    assert result["installed"] is True
    assert (Path(item["directory"]) / "resource_packs" / pack_id / "manifest.json").exists()
    assert content.resource_pack_info(item["id"])["required"] is True
    removed = content.remove_bedrock_resource_pack(item["id"], pack_id)
    assert removed["removed"] == pack_id
    assert not (Path(item["directory"]) / "resource_packs" / pack_id).exists()
