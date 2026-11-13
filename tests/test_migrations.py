import sqlite3
from mmanager import store
def test_old_registry_migrates_additively(monkeypatch,tmp_path):
 dbpath=tmp_path/"legacy.sqlite3"
 db=sqlite3.connect(dbpath)
 db.execute("CREATE TABLE servers(id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,edition TEXT NOT NULL,version TEXT NOT NULL,java_port INTEGER,bedrock_port INTEGER,directory TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
 db.execute("INSERT INTO servers(id,name,edition,version,java_port,directory) VALUES('id1','old','java','1.20.1',25565,'/old/world')")
 db.execute("INSERT INTO servers(id,name,edition,version,java_port,directory) VALUES('id2','old-bedrock','bedrock','1.26.33',19132,'/old/bedrock')")
 db.commit();db.close()
 monkeypatch.setattr(store,"DATA",tmp_path);monkeypatch.setattr(store,"DB",dbpath)
 row=store.get_server("id1")
 assert row["software"]=="vanilla" and row["directory"]=="/old/world"
 assert "bedrock_port" in row and row["eula_accepted"]==0
 assert row["ipv4_enabled"]==1 and row["ipv6_enabled"]==0
 assert row["ipv6_port"] is None
 bedrock=store.get_server("id2")
 assert bedrock["ipv4_enabled"]==1 and bedrock["ipv6_enabled"]==0
 assert bedrock["ipv6_port"]==19133
