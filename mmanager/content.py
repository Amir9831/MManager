"""World and resource-pack management for the single configured Minecraft server."""
import json
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path

from . import core, settings, store


def _server(sid):
    item = store.get_server(sid)
    if not item:
        raise core.ManagerError("GM-108: Server not found")
    return item


def _world_name(value):
    value = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9 _-]{1,48}", value):
        raise core.ManagerError("World name must be 1-48 letters, digits, underscores or hyphens.")
    return value


def _world_root(item):
    root = Path(item["directory"])
    return root / "worlds" if item["edition"] == "bedrock" else root


def _active_world_name(item):
    values = core.server_settings(item["id"])["settings"]
    return values.get("level-name") or ("Bedrock level" if item["edition"] == "bedrock" else "world")


def list_worlds(sid):
    item = _server(sid)
    root = _world_root(item)
    root.mkdir(parents=True, exist_ok=True)
    active = _active_world_name(item)
    worlds = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.is_symlink():
            continue
        if (path / "level.dat").is_file():
            worlds.append({"name": path.name, "active": path.name == active, "size_bytes": sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())})
    return {"active": active, "items": worlds, "edition": item["edition"]}


def _validate_zip(zf, max_expanded=8 * 1024**3):
    infos = zf.infolist()
    if not infos or len(infos) > 100000:
        raise core.ManagerError("Invalid archive: empty or too many entries.")
    total = 0
    for info in infos:
        name = info.filename.replace("\\", "/")
        parts = Path(name).parts
        mode = (info.external_attr >> 16) & 0xFFFF
        if name.startswith("/") or ".." in parts or (parts and ":" in parts[0]):
            raise core.ManagerError("Unsafe archive path rejected.")
        file_type = stat.S_IFMT(mode)
        if stat.S_ISLNK(mode) or file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise core.ManagerError("Archive contains an unsupported file type.")
        if info.is_dir() and file_type == stat.S_IFREG:
            raise core.ManagerError("Archive directory entry has an invalid file type.")
        total += info.file_size
        if total > max_expanded:
            raise core.ManagerError("Archive expands beyond the 8 GiB safety limit.")
    return infos


def upload_world(sid, name, fileobj, original_filename):
    item = _server(sid)
    name = _world_name(name)
    filename = str(original_filename or "").lower()
    accepted = (".mcworld", ".zip") if item["edition"] == "bedrock" else (".zip",)
    if not filename.endswith(accepted):
        raise core.ManagerError("Bedrock worlds must be .mcworld or .zip; Java worlds must be .zip.")
    if core._active(item):
        raise core.ManagerError("Stop the server before uploading a world.")
    root = _world_root(item)
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    if target.exists():
        raise core.ManagerError("A world with that name already exists.")
    core.create_backup(sid)
    with tempfile.TemporaryDirectory(prefix="mmanager-world-") as tmp:
        stage = Path(tmp) / "extract"
        stage.mkdir()
        try:
            fileobj.seek(0)
            with zipfile.ZipFile(fileobj) as zf:
                _validate_zip(zf)
                zf.extractall(stage)
        except (zipfile.BadZipFile, OSError) as exc:
            raise core.ManagerError("Invalid world ZIP: " + str(exc))
        candidates = [p.parent for p in stage.rglob("level.dat") if p.is_file()]
        if len(candidates) != 1:
            raise core.ManagerError("ZIP must contain exactly one Minecraft world with level.dat.")
        source = candidates[0]
        target.mkdir(mode=0o750)
        try:
            for child in source.iterdir():
                dest = target / child.name
                if child.is_dir():
                    shutil.copytree(child, dest, symlinks=False)
                elif child.is_file() and not child.is_symlink():
                    shutil.copy2(child, dest)
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
    return {"uploaded": True, "name": name, "active": False}


def activate_world(sid, name):
    item = _server(sid)
    name = _world_name(name)
    target = _world_root(item) / name
    if not target.is_dir() or target.is_symlink() or not (target / "level.dat").is_file():
        raise core.ManagerError("World not found or level.dat is missing.")
    was_active = core._active(item)
    if was_active:
        core._systemctl("stop", item)
    try:
        core.create_backup(sid)
        core.update_server_settings(sid, {"level-name": name})
        if was_active:
            core._systemctl("start", item)
        return {"activated": True, "name": name, "restarted": was_active}
    except Exception:
        if was_active:
            try:
                core._systemctl("start", item)
            except Exception:
                pass
        raise


def resource_pack_info(sid):
    item = _server(sid)
    if item["edition"] == "bedrock":
        world = _world_root(item) / _active_world_name(item)
        manifest = world / "world_resource_packs.json"
        packs = []
        if manifest.is_file():
            try:
                entries = json.loads(manifest.read_text())
                for entry in entries:
                    packs.append({"id": entry.get("pack_id"), "version": entry.get("version")})
            except (OSError, ValueError):
                raise core.ManagerError("Bedrock world resource-pack manifest is invalid.")
        return {"edition": "bedrock", "items": packs, "required": core.server_settings(sid)["settings"].get("texturepack-required", "false") == "true"}
    values = core.server_settings(sid)["settings"]
    return {"edition": item["edition"], "url": values.get("resource-pack", ""), "sha1": values.get("resource-pack-sha1", ""), "required": values.get("require-resource-pack", "false") == "true"}


def configure_java_resource_pack(sid, url, sha1, required):
    item = _server(sid)
    if item["edition"] == "bedrock":
        raise core.ManagerError("Use .mcpack upload for Bedrock Dedicated Server.")
    url = str(url or "").strip()
    sha1 = str(sha1 or "").strip().lower()
    if url and (not url.startswith("https://") or len(url) > 2048):
        raise core.ManagerError("Resource-pack URL must be an HTTPS URL.")
    if sha1 and not re.fullmatch(r"[a-f0-9]{40}", sha1):
        raise core.ManagerError("Resource-pack SHA-1 must contain exactly 40 hexadecimal characters.")
    return core.update_server_settings(sid, {
        "resource-pack": url,
        "resource-pack-sha1": sha1,
        "require-resource-pack": "true" if required else "false",
    })


def install_bedrock_resource_pack(sid, fileobj, original_filename, required=False):
    item = _server(sid)
    if item["edition"] != "bedrock":
        raise core.ManagerError(".mcpack upload is only supported by Bedrock Dedicated Server.")
    if not str(original_filename or "").lower().endswith(".mcpack"):
        raise core.ManagerError("Bedrock resource pack must be a .mcpack file.")
    if core._active(item):
        raise core.ManagerError("Stop the server before installing a resource pack.")
    root = Path(item["directory"])
    world = _world_root(item) / _active_world_name(item)
    if not world.is_dir():
        raise core.ManagerError("Active Bedrock world directory does not exist. Start the server once, then stop it before installing packs.")
    with tempfile.TemporaryDirectory(prefix="mmanager-pack-") as tmp:
        stage = Path(tmp)
        try:
            fileobj.seek(0)
            with zipfile.ZipFile(fileobj) as zf:
                _validate_zip(zf, max_expanded=1024**3)
                zf.extractall(stage)
        except (zipfile.BadZipFile, OSError) as exc:
            raise core.ManagerError("Invalid .mcpack archive: " + str(exc))
        manifests = list(stage.rglob("manifest.json"))
        if len(manifests) != 1:
            raise core.ManagerError("Resource pack must contain exactly one manifest.json.")
        manifest_path = manifests[0]
        try:
            manifest = json.loads(manifest_path.read_text())
            header = manifest["header"]
            pack_id = str(uuid.UUID(header["uuid"]))
            version = header["version"]
            if not isinstance(version, list) or len(version) != 3 or any(not isinstance(x, int) or x < 0 for x in version):
                raise ValueError("invalid version")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise core.ManagerError("Invalid Bedrock resource-pack manifest: " + str(exc))
        pack_root = manifest_path.parent
        packs_dir = root / "resource_packs"
        packs_dir.mkdir(parents=True, exist_ok=True)
        target = packs_dir / pack_id
        if target.exists():
            raise core.ManagerError("This resource pack is already installed.")
        core.create_backup(sid)
        shutil.copytree(pack_root, target, symlinks=False)
    manifest_file = world / "world_resource_packs.json"
    entries = []
    if manifest_file.is_file():
        try:
            entries = json.loads(manifest_file.read_text())
            if not isinstance(entries, list):
                raise ValueError("expected list")
        except (OSError, ValueError):
            raise core.ManagerError("Existing world_resource_packs.json is invalid.")
    entries = [x for x in entries if x.get("pack_id") != pack_id]
    entries.append({"pack_id": pack_id, "version": version})
    manifest_file.write_text(json.dumps(entries, indent=2) + "\n")
    core.update_server_settings(sid, {"texturepack-required": "true" if required else "false"})
    return {"installed": True, "id": pack_id, "version": version, "required": bool(required)}


def remove_bedrock_resource_pack(sid, pack_id):
    item = _server(sid)
    if item["edition"] != "bedrock":
        raise core.ManagerError("Resource-pack file removal is available only for Bedrock.")
    try:
        pack_id = str(uuid.UUID(str(pack_id)))
    except ValueError:
        raise core.ManagerError("Invalid resource-pack ID.")
    if core._active(item):
        raise core.ManagerError("Stop the server before removing a resource pack.")
    world = _world_root(item) / _active_world_name(item)
    manifest_file = world / "world_resource_packs.json"
    entries = json.loads(manifest_file.read_text()) if manifest_file.exists() else []
    updated = [x for x in entries if x.get("pack_id") != pack_id]
    if len(updated) == len(entries):
        raise core.ManagerError("Resource pack is not assigned to the active world.")
    core.create_backup(sid)
    manifest_file.write_text(json.dumps(updated, indent=2) + "\n")
    shutil.rmtree(Path(item["directory"]) / "resource_packs" / pack_id, ignore_errors=True)
    return {"removed": pack_id}
