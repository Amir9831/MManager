import pytest
from pathlib import Path
from mmanager import core,store,settings
def setup(monkeypatch,tmp_path):
 monkeypatch.setattr(store,"DATA",tmp_path/"data"); monkeypatch.setattr(store,"DB",tmp_path/"data"/"test.db")
 monkeypatch.setattr(settings,"SERVERS",tmp_path/"servers")
 monkeypatch.setattr(core,"_vanilla",lambda v:"https://invalid.test/server.jar")
 monkeypatch.setattr(core,"_download",lambda u,d:Path(d).write_bytes(b"x"*2048))
 monkeypatch.setattr(core,"choose_port",lambda p,proto,reserved:p if p not in reserved else p+1)
def test_create_and_eula(monkeypatch,tmp_path):
 setup(monkeypatch,tmp_path)
 x=core.create_server("survival","java","1.21.4","vanilla",True)
 assert store.get_server(x["id"])["java_port"]==25565
 assert (tmp_path/"servers"/"survival"/"eula.txt").read_text()=="eula=true\n"
def test_eula_required(monkeypatch,tmp_path):
 setup(monkeypatch,tmp_path)
 with pytest.raises(core.ManagerError,match="GM-106"):core.create_server("survival","java","1.21.4")
def test_invalid_name():
 with pytest.raises(core.ManagerError,match="GM-101"):core.create_server("../x","java","1.21.4","vanilla",True)
