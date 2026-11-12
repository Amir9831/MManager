import json
import pytest
from pathlib import Path
from mmanager import advanced,core,settings,store

def test_player_moderation_builds_safe_commands(monkeypatch):
    monkeypatch.setattr(advanced,"_server",lambda sid:{"id":sid,"edition":"java"})
    calls=[]
    monkeypatch.setattr(advanced,"_rcon",lambda item,cmd:calls.append(cmd) or "ok")
    result=advanced.moderate("id","ban","Steve","griefing")
    assert result["response"]=="ok"
    assert calls==["ban Steve griefing"]
    with pytest.raises(core.ManagerError):
        advanced.moderate("id","ban","../root")

def test_bedrock_rcon_is_explicitly_unsupported(tmp_path):
    with pytest.raises(core.ManagerError,match="not supported"):
        advanced._rcon({"edition":"bedrock","directory":str(tmp_path)},"list")

def test_update_and_rollback_preserve_previous_binary(monkeypatch,tmp_path):
    monkeypatch.setattr(store,"DATA",tmp_path/"data")
    monkeypatch.setattr(store,"DB",tmp_path/"data"/"test.db")
    monkeypatch.setattr(settings,"SERVERS",tmp_path/"servers")
    monkeypatch.setattr(settings,"BACKUPS",tmp_path/"backups")
    monkeypatch.setattr(settings,"ROOT",tmp_path/"root")
    monkeypatch.setattr(core,"choose_port",lambda p,proto,reserved:p)
    monkeypatch.setattr(core,"_vanilla",lambda v:{"url":"https://invalid.test/"+v+".jar","checksum":None,"algorithm":"sha1"})
    def download(url,dest,*args):
        Path(dest).write_bytes((url.encode()+b"x"*2048)[:4096])
    monkeypatch.setattr(core,"_download",download)
    monkeypatch.setattr(core,"_active",lambda item:False)
    monkeypatch.setattr(core,"_systemctl",lambda action,item:None)
    item=core.create_server("survival","java","1.21.4","vanilla",True)
    jar=Path(item["directory"])/"server.jar"
    before=jar.read_bytes()
    result=core.update_server(item["id"],"1.21.5")
    assert result["updated"] is True
    assert store.get_server(item["id"])["version"]=="1.21.5"
    assert jar.read_bytes()!=before
    rolled=core.rollback_server(item["id"])
    assert rolled["rolled_back"] is True
    assert store.get_server(item["id"])["version"]=="1.21.4"
    assert jar.read_bytes()==before

def test_bedrock_update_preserves_world_and_settings(monkeypatch,tmp_path):
    import zipfile
    monkeypatch.setattr(store,"DATA",tmp_path/"data")
    monkeypatch.setattr(store,"DB",tmp_path/"data"/"test.db")
    monkeypatch.setattr(settings,"SERVERS",tmp_path/"servers")
    monkeypatch.setattr(settings,"BACKUPS",tmp_path/"backups")
    monkeypatch.setattr(settings,"ROOT",tmp_path/"root")
    monkeypatch.setattr(core,"choose_port",lambda p,proto,reserved:p)
    monkeypatch.setattr(core,"_bedrock",lambda v:{"url":"https://invalid.test/"+v+".zip","checksum":None,"algorithm":"sha256"})
    current={"version":"1.26.63"}
    def download(url,dest,*args):
        binary=("BDS-"+url.rsplit("/",1)[-1]).encode()
        with zipfile.ZipFile(dest,"w") as z:
            z.writestr("bedrock_server",binary)
            z.writestr("server.properties","server-name=archive-default\n")
    monkeypatch.setattr(core,"_download",download)
    monkeypatch.setattr(core,"_active",lambda item:False)
    monkeypatch.setattr(core,"_systemctl",lambda action,item:None)
    item=core.create_server("bedrock","bedrock","1.26.63","bedrock",True)
    root=Path(item["directory"])
    (root/"worlds").mkdir()
    (root/"worlds"/"world.db").write_text("important world")
    (root/"server.properties").write_text("server-name=My Server\n")
    before=(root/"bedrock_server").read_bytes()
    result=core.update_server(item["id"],"1.26.64")
    assert result["updated"] is True
    assert (root/"bedrock_server").read_bytes()!=before
    assert (root/"worlds"/"world.db").read_text()=="important world"
    assert (root/"server.properties").read_text()=="server-name=My Server\n"
    core.rollback_server(item["id"])
    assert (root/"bedrock_server").read_bytes()==before
    assert (root/"worlds"/"world.db").read_text()=="important world"
    assert store.get_server(item["id"])["version"]=="1.26.63"

def test_rcon_reassembles_multiple_packets(monkeypatch,tmp_path):
    import struct
    props=tmp_path/"server.properties"
    props.write_text("enable-rcon=true\nrcon.password=long-password-value\nrcon.port=25575\n")
    def response(reqid,payload):
        body=struct.pack("<ii",reqid,0)+payload.encode()+b"\0\0"
        return struct.pack("<i",len(body))+body
    class FakeSocket:
        def __init__(self):
            self.data=bytearray(response(11,"")+response(12,"first")+response(12," second")+response(13,""))
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def settimeout(self,value): pass
        def sendall(self,data): pass
        def recv(self,size):
            chunk=self.data[:size];del self.data[:size];return bytes(chunk)
    monkeypatch.setattr(advanced.socket,"create_connection",lambda *a,**k:FakeSocket())
    result=advanced._rcon({"edition":"java","directory":str(tmp_path)},"list")
    assert result=="first second"


def test_proc_stat_parser_handles_spaces_in_process_name():
    # Fields after the final ')' start at field 3; utime/stime are fields 14/15.
    raw = "123 (java server worker) S " + " ".join(str(i) for i in range(1, 30))
    assert advanced._proc_cpu_ticks(raw) == 11 + 12


def _setup_player_tests(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    monkeypatch.setattr(store, "DB", tmp_path / "data" / "test.db")
    monkeypatch.setattr(settings, "SERVERS", tmp_path / "servers")
    monkeypatch.setattr(core, "_vanilla", lambda v: {"url": "https://invalid.test/server.jar", "checksum": None, "algorithm": "sha1"})
    monkeypatch.setattr(core, "_paper", lambda v: {"url": "https://invalid.test/paper.jar", "checksum": None, "algorithm": "sha256"})
    monkeypatch.setattr(core, "_bedrock", lambda v: {"url": "https://invalid.test/bds.zip", "checksum": None, "algorithm": "sha256"})
    def download(url, dest, *args):
        if str(dest).endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(dest, "w") as z:
                z.writestr("bedrock_server", b"fake-bds-binary")
        else:
            Path(dest).write_bytes(b"x" * 2048)
    monkeypatch.setattr(core, "_download", download)
    monkeypatch.setattr(core, "choose_port", lambda p, proto, reserved: p if p not in reserved else p + 1)


def test_java_player_lists_include_offline_admin_and_banned(monkeypatch, tmp_path):
    _setup_player_tests(monkeypatch, tmp_path)
    item = core.create_server("java", "java", "1.21.4", "vanilla", True)
    root = Path(item["directory"])
    (root / "usercache.json").write_text(json.dumps([{"name": "Alex", "uuid": "a"}, {"name": "Steve", "uuid": "b"}]))
    (root / "ops.json").write_text(json.dumps([{"name": "Alex", "uuid": "a", "level": 3}]))
    (root / "whitelist.json").write_text("[]")
    (root / "banned-players.json").write_text(json.dumps([{"name": "Steve", "uuid": "b"}]))
    monkeypatch.setattr(advanced, "_rcon", lambda item, command: "There are 1 of a max of 20 players online: Alex")
    data = advanced.players(item["id"])
    assert [x["name"] for x in data["online"]] == ["Alex"]
    assert [x["name"] for x in data["offline"]] == ["Steve"]
    assert data["admins"][0]["level"] == 3
    assert data["offline"][0]["banned"] is True


def test_bedrock_player_lists_and_permissions(monkeypatch, tmp_path):
    _setup_player_tests(monkeypatch, tmp_path)
    item = core.create_server("bedrock", "bedrock", "1.26.63", "bedrock", True)
    root = Path(item["directory"])
    (root / "allowlist.json").write_text(json.dumps([{"name": "Builder", "xuid": "12345"}, {"name": "Guest", "xuid": "67890"}]))
    (root / "permissions.json").write_text(json.dumps([{"permission": "operator", "xuid": "12345"}]))
    monkeypatch.setattr(advanced, "_bedrock_online", lambda item: [{"name": "Builder", "xuid": "12345", "online": True}])
    monkeypatch.setattr(advanced, "console", lambda sid, command: {"response": command})
    monkeypatch.setattr(advanced, "_active", lambda item: True)
    data = advanced.players(item["id"])
    assert [x["name"] for x in data["online"]] == ["Builder"]
    assert [x["name"] for x in data["offline"]] == ["Guest"]
    assert data["admins"][0]["name"] == "Builder"
    result = advanced.moderate(item["id"], "permission", "Guest", permission="visitor")
    assert result["response"] == "permission reload"
    permissions = json.loads((root / "permissions.json").read_text())
    assert {"permission": "visitor", "xuid": "67890"} in permissions


def test_bedrock_console_fifo_wrapper(monkeypatch, tmp_path):
    _setup_player_tests(monkeypatch, tmp_path)
    item = core.create_server("bedrock", "bedrock", "1.26.63", "bedrock", True)
    assert advanced.ensure_bedrock_console(item) is True
    script = (Path(item["directory"]) / "run.sh").read_text()
    assert ".mmanager-console.fifo" in script
    assert "exec 3<>" in script
    assert advanced.ensure_bedrock_console(item) is False


def test_java_online_players_use_file_backed_service_logs(monkeypatch, tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(advanced, "SERVER_LOG_DIR", log_dir)
    (log_dir / "java-test.log").write_text(
        "[Server thread/INFO]: Alex joined the game\\n"
        "[Server thread/INFO]: Steve joined the game\\n"
        "[Server thread/INFO]: Alex left the game\\n"
    )
    assert advanced._java_online_from_logs({"name": "java-test"}) == [
        {"name": "Steve", "online": True}
    ]


def test_bedrock_online_players_use_file_backed_service_logs(monkeypatch, tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(advanced, "SERVER_LOG_DIR", log_dir)
    (log_dir / "bedrock-test.log").write_text(
        "Player connected: Alex, xuid: 12345\\n"
        "Player disconnected: Alex, xuid: 12345\\n"
        "Player connected: Steve, xuid: 67890\\n"
    )
    assert advanced._bedrock_online({"name": "bedrock-test"}) == [
        {"name": "Steve", "xuid": "67890", "online": True}
    ]
