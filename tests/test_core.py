import pytest
from pathlib import Path
from mmanager import core,store,settings
def setup(monkeypatch,tmp_path):
 monkeypatch.setattr(store,"DATA",tmp_path/"data");monkeypatch.setattr(store,"DB",tmp_path/"data"/"test.db")
 monkeypatch.setattr(settings,"SERVERS",tmp_path/"servers")
 monkeypatch.setattr(core,"_vanilla",lambda v:{"url":"https://invalid.test/server.jar","checksum":None,"algorithm":"sha1"})
 monkeypatch.setattr(core,"_paper",lambda v:{"url":"https://invalid.test/paper.jar","checksum":None,"algorithm":"sha256"})
 monkeypatch.setattr(core,"_download",lambda u,d,*a:Path(d).write_bytes(b"x"*2048))
 monkeypatch.setattr(core,"choose_port",lambda p,proto,reserved:p if p not in reserved else p+1)
def test_create_and_eula(monkeypatch,tmp_path):
 setup(monkeypatch,tmp_path);x=core.create_server("survival","java","1.21.4","vanilla",True)
 assert store.get_server(x["id"])["java_port"]==25565
 assert (tmp_path/"servers"/"survival"/"eula.txt").read_text()=="eula=true\n"
def test_eula_required(monkeypatch,tmp_path):
 setup(monkeypatch,tmp_path)
 with pytest.raises(core.ManagerError,match="GM-106"):core.create_server("survival","java","1.21.4")
def test_invalid_name():
 with pytest.raises(core.ManagerError,match="GM-101"):core.create_server("../x","java","1.21.4","vanilla",True)
def test_crossplay_allocates_udp_and_config(monkeypatch,tmp_path):
 setup(monkeypatch,tmp_path);x=core.create_server("cross","crossplay","1.21.4","paper",True)
 assert x["bedrock_port"]==19132
 assert "port: 19132" in (tmp_path/"servers"/"cross"/"plugins"/"Geyser-Spigot"/"config.yml").read_text()

def test_bedrock_release_catalog(monkeypatch):
    from mmanager import core
    monkeypatch.setattr(core, "_json", lambda url: {"release":{"latest":"1.26.63","versions":["1.26.63","1.26.62"]}})
    data=core.available_versions("bedrock")
    assert data["latest"]=="1.26.63"
    assert [x["id"] for x in data["versions"]]==["1.26.63","1.26.62"]

def test_server_settings_templates_and_validation(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    item=core.create_server("settings","java","1.21.4","vanilla",True)
    values=core.server_settings(item["id"])["settings"]
    assert values["max-players"]=="20"
    assert values["online-mode"]=="true"
    core.update_server_settings(item["id"],{"motd":"Hello: MManager","max-players":"32"})
    saved=core.server_settings(item["id"])["settings"]
    assert saved["motd"]=="Hello: MManager"
    assert saved["max-players"]=="32"
    with pytest.raises(core.ManagerError,match="GM-240"):
        core.update_server_settings(item["id"],{"bad key":"x"})

def test_bedrock_install_uses_verified_zip(monkeypatch,tmp_path):
    import zipfile
    setup(monkeypatch,tmp_path)
    monkeypatch.setattr(core,"_bedrock",lambda v:{"url":"https://invalid.test/bds.zip","checksum":None,"algorithm":"sha256"})
    def fake_download(url,dest,*args):
        with zipfile.ZipFile(dest,"w") as archive:
            archive.writestr("bedrock_server",b"fake executable")
        return dest.stat().st_size
    monkeypatch.setattr(core,"_download",fake_download)
    item=core.create_server("bedrock","bedrock","1.26.63","bedrock",True)
    root=tmp_path/"servers"/"bedrock"
    assert item["java_port"]==19132
    assert (root/"bedrock_server").exists()
    assert "LD_LIBRARY_PATH" in (root/"run.sh").read_text()
    assert "server-port=19132" in (root/"server.properties").read_text()


def test_server_logs_read_rotated_file_tail_without_subprocess(monkeypatch, tmp_path):
 setup(monkeypatch,tmp_path)
 item=core.create_server("logs","java","1.21.4","vanilla",True)
 log_dir=tmp_path/"logs"
 log_dir.mkdir()
 monkeypatch.setattr(core,"SERVER_LOG_DIR",log_dir)
 (log_dir/"logs.log").write_text("line 1\nline 2\nline 3\n")
 def forbidden(*args,**kwargs):
  raise AssertionError("server_logs must read the service log file directly")
 monkeypatch.setattr(core.subprocess,"run",forbidden)
 assert core.server_logs(item["id"],2)=="line 2\nline 3\n"
 assert core.server_logs(item["id"],1)=="line 3\n"


def test_backup_download_and_delete_are_scoped_and_safe(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    item=core.create_server("backupops","java","1.21.4","vanilla",True)
    monkeypatch.setattr(core.settings,"BACKUPS",tmp_path/"backups")
    core.settings.BACKUPS.mkdir()
    archive=core.settings.BACKUPS/"backupops-test.tar.gz"
    archive.write_bytes(b"backup-data")
    bid="backup-test-id"
    store.add_backup({"id":bid,"server_id":item["id"],"filename":str(archive),"size":archive.stat().st_size})
    assert core.backup_file(item["id"],bid)==archive.resolve()
    assert core.delete_backup(item["id"],bid)=={"deleted":True,"id":bid}
    assert not archive.exists()
    assert store.get_backup(item["id"],bid) is None


def test_backup_path_rejects_files_outside_backup_directory(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    item=core.create_server("backupunsafe","java","1.21.4","vanilla",True)
    monkeypatch.setattr(core.settings,"BACKUPS",tmp_path/"backups")
    core.settings.BACKUPS.mkdir()
    outside=tmp_path/"outside.tar.gz"
    outside.write_bytes(b"not a backup")
    bid="outside-id"
    store.add_backup({"id":bid,"server_id":item["id"],"filename":str(outside),"size":outside.stat().st_size})
    with pytest.raises(core.ManagerError,match="GM-236"):
        core.backup_file(item["id"],bid)


def test_switch_java_to_crossplay_preserves_world_and_updates_registry(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    item=core.create_server("switchcp","java","1.21.4","vanilla",True)
    root=Path(item["directory"])
    (root/"world").mkdir()
    (root/"world"/"level.dat").write_bytes(b"world")
    monkeypatch.setattr(core,"_active",lambda item:False)
    monkeypatch.setattr(core,"_systemctl",lambda action,item:None)
    monkeypatch.setattr(core,"create_backup",lambda sid:{"id":"backup-switch","filename":"backup.tar.gz"})
    def runtime(stage,edition,software,version,java_port,bedrock_port):
        (stage/"server.jar").write_bytes(b"new-runtime")
        if edition=="crossplay":
            plugin=stage/"plugins"/"Geyser-Spigot"
            plugin.mkdir(parents=True,exist_ok=True)
            (plugin/"config.yml").write_text("bedrock:\n  port: "+str(bedrock_port)+"\nremote:\n  port: "+str(java_port)+"\n")
            (stage/"plugins"/"Geyser-Spigot.jar").write_bytes(b"geyser")
            (stage/"plugins"/"floodgate-spigot.jar").write_bytes(b"floodgate")
        (stage/"server.properties").write_text("server-port="+str(java_port)+"\n")
        (stage/"run.sh").write_text("#!/bin/sh\n")
    monkeypatch.setattr(core,"_write_server_runtime",runtime)
    result=core.switch_server(item["id"],"crossplay","paper","1.21.4",False)
    saved=store.get_server(item["id"])
    assert result["switched"] is True
    assert saved["edition"]=="crossplay" and saved["software"]=="paper"
    assert saved["bedrock_port"]==19132
    assert (root/"world"/"level.dat").read_bytes()==b"world"


def test_switch_java_to_bedrock_archives_old_world_and_uses_new_runtime(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    item=core.create_server("switchbd","java","1.21.4","vanilla",True)
    root=Path(item["directory"])
    (root/"world").mkdir()
    (root/"world"/"level.dat").write_bytes(b"java-world")
    monkeypatch.setattr(core,"_active",lambda item:False)
    monkeypatch.setattr(core,"_systemctl",lambda action,item:None)
    monkeypatch.setattr(core,"create_backup",lambda sid:{"id":"backup-switch","filename":"backup.tar.gz"})
    def runtime(stage,edition,software,version,java_port,bedrock_port):
        (stage/"bedrock_server").write_bytes(b"bedrock-runtime")
        (stage/"server.properties").write_text("server-port="+str(java_port)+"\n")
        (stage/"run.sh").write_text("#!/bin/sh\n")
    monkeypatch.setattr(core,"_write_server_runtime",runtime)
    result=core.switch_server(item["id"],"bedrock","bedrock","1.26.63",True)
    saved=store.get_server(item["id"])
    archives=list(root.parent.glob("switchbd.archived-*"))
    assert result["world_archived"] is True
    assert saved["edition"]=="bedrock" and saved["software"]=="bedrock"
    assert (root/"bedrock_server").exists()
    assert not (root/"world").exists()
    assert archives and (archives[0]/"world"/"level.dat").read_bytes()==b"java-world"


def test_active_treats_failed_known_unit_as_stopped(monkeypatch):
    class Result:
        returncode=3
        stdout="failed\n"
        stderr=""
    monkeypatch.setattr(core.subprocess,"run",lambda *args,**kwargs:Result())
    assert core._active({"name":"broken-server"}) is False


def test_active_still_rejects_unknown_systemd_unit(monkeypatch):
    class Result:
        returncode=4
        stdout="unknown\n"
        stderr=""
    monkeypatch.setattr(core.subprocess,"run",lambda *args,**kwargs:Result())
    with pytest.raises(core.ManagerError,match="GM-222"):
        core._active({"name":"missing-server"})


def test_bedrock_cdn_download_uses_browser_user_agent(monkeypatch, tmp_path):
    import io
    seen = []
    payload = b"x" * 2048

    def fake_urlopen(request, timeout=60):
        seen.append(request.get_header("User-agent"))
        return io.BytesIO(payload)

    monkeypatch.setattr(core.urllib.request, "urlopen", fake_urlopen)
    target = tmp_path / "bedrock.zip"
    core._download("https://www.minecraft.net/bedrockdedicatedserver/bin-linux/test.zip", target)
    assert seen == ["Mozilla/5.0"]
    assert target.read_bytes() == payload


def test_other_downloads_keep_mmanager_user_agent(monkeypatch, tmp_path):
    import io
    seen = []

    def fake_urlopen(request, timeout=60):
        seen.append(request.get_header("User-agent"))
        return io.BytesIO(b"x" * 2048)

    monkeypatch.setattr(core.urllib.request, "urlopen", fake_urlopen)
    core._download("https://example.com/server.jar", tmp_path / "server.jar")
    assert seen == ["MManager/0.2 (https://github.com/Amir9831/MManager)"]



def test_bedrock_udp_allocation_does_not_reserve_java_tcp_ports(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    with store.connect() as db:
        db.execute(
            "INSERT INTO servers(id,name,edition,software,version,java_port,bedrock_port,directory,eula_accepted) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            ("java-id", "javaexisting", "java", "vanilla", "1.21.4", 19132, None,
             str(tmp_path / "servers" / "javaexisting"), 1),
        )
    calls = []

    def choose(preferred, protocol, reserved=None, **kwargs):
        calls.append((preferred, protocol, set(reserved or set())))
        return preferred

    monkeypatch.setattr(core, "choose_port", choose)
    item = core.create_server("bedrockudp", "bedrock", "1.26.63", "bedrock", True)
    assert item["java_port"] == 19132
    assert calls == [(19132, "udp", set())]


def test_bedrock_status_detects_wrong_udp_port(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    item = {
        "id": "status-id", "name": "minecraft", "edition": "bedrock",
        "software": "bedrock", "version": "1.26.63", "java_port": 19132,
        "bedrock_port": None, "directory": str(tmp_path / "servers" / "minecraft"),
    }
    with store.connect() as db:
        db.execute(
            "INSERT INTO servers(id,name,edition,software,version,java_port,bedrock_port,directory,eula_accepted) "
            "VALUES(:id,:name,:edition,:software,:version,:java_port,:bedrock_port,:directory,1)",
            item,
        )

    class Result:
        returncode = 0
        stdout = "UNCONN 0 0 *:7551 *:* users:((\"bedrock_server\",pid=8907,fd=18))\\n"
        stderr = ""

    monkeypatch.setattr(core, "_active", lambda _: True)
    monkeypatch.setattr(core.shutil, "which", lambda _: "/usr/bin/ss")

    def fake_run(args, **kwargs):
        if args[0] == "/usr/bin/systemctl":
            return type("PidResult", (), {"returncode": 0, "stdout": "8907", "stderr": ""})()
        return Result()

    monkeypatch.setattr(core.subprocess, "run", fake_run)

    status = core.server_status("status-id")
    assert status["status"] == "degraded"
    assert status["health"] == "degraded"
    assert status["expected"] == [{"protocol": "udp", "port": 19132}]
    assert "UDP/19132" in status["error"]



def test_crossplay_udp_allocation_reserves_existing_bedrock_udp(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    with store.connect() as db:
        db.execute(
            "INSERT INTO servers(id,name,edition,software,version,java_port,bedrock_port,directory,eula_accepted) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            ("bedrock-id", "bedrockexisting", "bedrock", "bedrock", "1.26.63", 19132, None,
             str(tmp_path / "servers" / "bedrockexisting"), 1),
        )
    item = core.create_server("crossudp", "crossplay", "1.21.4", "paper", True)
    assert item["bedrock_port"] == 19133


def test_tcp_and_udp_can_share_same_numeric_port(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    with store.connect() as db:
        db.execute(
            "INSERT INTO servers(id,name,edition,software,version,java_port,bedrock_port,directory,eula_accepted) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            ("java-id", "javaexisting", "java", "vanilla", "1.21.4", 19132, None,
             str(tmp_path / "servers" / "javaexisting"), 1),
        )
    item = core.create_server("bedrockshare", "bedrock", "1.26.63", "bedrock", True)
    assert item["java_port"] == 19132
