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
