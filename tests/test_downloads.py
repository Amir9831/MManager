import hashlib,io,json
import pytest
from mmanager import core

def test_paper_uses_first_stable_build_and_sha256(monkeypatch):
 payload=[{"id":2,"channel":"EXPERIMENTAL","downloads":{}},{"id":1,"channel":"STABLE","downloads":{"server:default":{"url":"https://fill-data.papermc.io/server.jar","checksums":{"sha256":"abc"}}}}]
 monkeypatch.setattr(core.urllib.request,"urlopen",lambda req,timeout:io.BytesIO(json.dumps(payload).encode()))
 result=core._paper("1.21.4")
 assert result["url"].endswith("server.jar") and result["checksum"]=="abc"

def test_download_rejects_checksum_mismatch(monkeypatch,tmp_path):
 monkeypatch.setattr(core.urllib.request,"urlopen",lambda req,timeout:io.BytesIO(b"x"*2048))
 dest=tmp_path/"server.jar"
 with pytest.raises(core.ManagerError,match="GM-215"):core._download("https://example.invalid/server.jar",dest,"0"*64)
 assert not dest.exists()
