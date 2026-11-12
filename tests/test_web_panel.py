from fastapi.testclient import TestClient
from mmanager.api import public_app
from mmanager import webconfig

def test_public_panel_requires_secret_path(monkeypatch, tmp_path):
    monkeypatch.setattr(webconfig, "CONFIG", tmp_path)
    monkeypatch.setattr(webconfig, "WEB_FILE", tmp_path / "web.json")
    webconfig.save({"path": "a" * 32, "port": 8766})
    client = TestClient(public_app)
    assert client.get("/").status_code == 404
    assert client.get("/" + "a" * 32 + "/api/health").json()["status"] == "ok"
    response = client.get("/" + "a" * 32 + "/")
    assert response.status_code == 200
    assert "MManager" in response.text
