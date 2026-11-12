import os,sqlite3
from contextlib import contextmanager
from pathlib import Path
DATA=Path(os.environ.get("MMANAGER_DATA","/var/lib/mmanager")); DB=DATA/"mmanager.sqlite3"
@contextmanager
def connect():
 DATA.mkdir(parents=True,exist_ok=True); db=sqlite3.connect(DB,timeout=30,isolation_level=None); db.row_factory=sqlite3.Row
 try:
  db.execute("PRAGMA foreign_keys=ON"); db.execute("PRAGMA busy_timeout=30000")
  db.execute("""CREATE TABLE IF NOT EXISTS servers(id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,edition TEXT NOT NULL,software TEXT NOT NULL DEFAULT 'vanilla',version TEXT NOT NULL,java_port INTEGER,bedrock_port INTEGER,directory TEXT NOT NULL,eula_accepted INTEGER NOT NULL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
  # Additive migrations keep the 0.1 registry and all world paths intact.
  cols={r[1] for r in db.execute("PRAGMA table_info(servers)")}
  for name,definition in (("software","TEXT NOT NULL DEFAULT 'vanilla'"),("eula_accepted","INTEGER NOT NULL DEFAULT 0"),("bedrock_port","INTEGER")):
   if name not in cols: db.execute(f"ALTER TABLE servers ADD COLUMN {name} {definition}")
  db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_servers_java_port ON servers(java_port) WHERE java_port IS NOT NULL")
  db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_servers_bedrock_port ON servers(bedrock_port) WHERE bedrock_port IS NOT NULL")
  db.execute("""CREATE TABLE IF NOT EXISTS backups(id TEXT PRIMARY KEY,server_id TEXT NOT NULL,filename TEXT NOT NULL,size INTEGER NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE)""")
  yield db
 finally:db.close()
def list_servers():
 with connect() as db:return [dict(r) for r in db.execute("SELECT * FROM servers ORDER BY name")]
def get_server(sid):
 with connect() as db:
  r=db.execute("SELECT * FROM servers WHERE id=?",(sid,)).fetchone();return dict(r) if r else None
def add_backup(x):
 with connect() as db:db.execute("INSERT INTO backups(id,server_id,filename,size) VALUES(:id,:server_id,:filename,:size)",x)
def list_backups(sid):
 with connect() as db:return [dict(r) for r in db.execute("SELECT * FROM backups WHERE server_id=? ORDER BY created_at DESC",(sid,))]
def get_backup(sid,bid):
 with connect() as db:
  row=db.execute("SELECT * FROM backups WHERE server_id=? AND id=?",(sid,bid)).fetchone()
  return dict(row) if row else None
def delete_backup(sid,bid):
 with connect() as db:
  cur=db.execute("DELETE FROM backups WHERE server_id=? AND id=?",(sid,bid))
  return cur.rowcount==1

def update_server_version(sid,version):
 with connect() as db:
  cur=db.execute("UPDATE servers SET version=? WHERE id=?",(version,sid))
  if cur.rowcount!=1: raise ValueError("Server not found")
