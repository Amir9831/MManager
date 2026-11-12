import json, secrets
from pathlib import Path
from .settings import CONFIG

WEB_FILE = CONFIG / "web.json"
DEFAULT_PORT = 8766

def load():
    try:
        data = json.loads(WEB_FILE.read_text())
    except (OSError, ValueError):
        data = {}
    path = str(data.get("path", "")).strip("/")
    port = data.get("port", DEFAULT_PORT)
    if not path or len(path) < 24 or not path.replace("-", "").replace("_", "").isalnum():
        path = secrets.token_urlsafe(24)
    if not isinstance(port, int) or not 1024 <= port <= 65535:
        port = DEFAULT_PORT
    return {"path": path, "port": port}

def save(data):
    CONFIG.mkdir(parents=True, exist_ok=True)
    tmp = WEB_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.chmod(0o640)
    tmp.replace(WEB_FILE)

def ensure():
    data = load()
    save(data)
    return data
