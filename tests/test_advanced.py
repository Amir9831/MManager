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
