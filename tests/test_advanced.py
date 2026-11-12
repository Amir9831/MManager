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
    assert advanced._proc_cpu_ticks(raw) == 12 + 13
