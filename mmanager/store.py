import os, sqlite3
from pathlib import Path
DATA=Path(os.environ.get('MMANAGER_DATA','/var/lib/mmanager')); DB=DATA/'mmanager.sqlite3'
def connect():
    DATA.mkdir(parents=True,exist_ok=True); db=sqlite3.connect(DB,timeout=15); db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS servers (id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,edition TEXT NOT NULL,version TEXT NOT NULL,java_port INTEGER,bedrock_port INTEGER,directory TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)'); db.commit(); return db
def list_servers():
    with connect() as db: return [dict(r) for r in db.execute('SELECT * FROM servers ORDER BY name')]
def add_server(s):
    with connect() as db: db.execute('INSERT INTO servers(id,name,edition,version,java_port,bedrock_port,directory) VALUES(:id,:name,:edition,:version,:java_port,:bedrock_port,:directory)',s)
def remove_server(sid):
    with connect() as db: return db.execute('DELETE FROM servers WHERE id=?',(sid,)).rowcount>0
