from fastapi.testclient import TestClient
from mmanager.api import app
def test_health(): assert TestClient(app).get("/api/health").status_code==200
def test_auth_required(): assert TestClient(app).get("/api/servers").status_code==401

def test_server_status_requires_auth():
    assert TestClient(app).get("/api/servers/example/status").status_code == 401
