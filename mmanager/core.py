import json,re,secrets,shutil,subprocess,tarfile,urllib.request,uuid,os
from pathlib import Path
from . import store,settings
from .ports import choose_port
NAME=re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,31}$")
class ManagerError(Exception): pass
def _json(url):
 req=urllib.request.Request(url,headers={"User-Agent":"MManager/0.2"})
 with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)
def _download(url,dest):
 tmp=Path(str(dest)+".part"); total=0
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"MManager/0.2"})
  with urllib.request.urlopen(req,timeout=60) as r,tmp.open("wb") as out:
   while True:
    chunk=r.read(1024*1024)
    if not chunk:break
    total+=len(chunk)
    if total>1024**3:raise ManagerError("GM-210: Download exceeds 1 GiB")
    out.write(chunk)
  if total<1024:raise ManagerError("GM-211: Download unexpectedly small")
  tmp.replace(dest)
 finally:
  if tmp.exists():tmp.unlink()
def _vanilla(version):
 m=_json("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json")
 v=next((x for x in m["versions"] if x["id"]==version and x["type"] in ("release","snapshot")),None)
 if not v:raise ManagerError("GM-212: Minecraft version not found")
 url=_json(v["url"]).get("downloads",{}).get("server",{}).get("url")
 if not url:raise ManagerError("GM-213: No server jar for this version")
 return url
def _paper(version):
 base="https://api.papermc.io/v2/projects/paper"; builds=_json(f"{base}/versions/{version}").get("builds",[])
 if not builds:raise ManagerError("GM-214: No Paper builds for this version")
 b=builds[-1]; d=_json(f"{base}/versions/{version}/builds/{b}")
 return f"{base}/versions/{version}/builds/{b}/downloads/{d['downloads']['application']['name']}"
def create_server(name,edition="java",version="1.21.4",software="vanilla",accept_eula=False):
 if not NAME.fullmatch(name):raise ManagerError("GM-101: Invalid server name")
 if edition not in {"java","crossplay"}:raise ManagerError("GM-102: Bedrock-only is not supported in this release")
 if software not in {"vanilla","paper"} or (edition=="crossplay" and software!="paper"):raise ManagerError("GM-103: Crossplay requires Paper")
 if not re.fullmatch(r"[A-Za-z0-9._-]{1,40}",version):raise ManagerError("GM-105: Invalid Minecraft version")
 if accept_eula is not True:raise ManagerError("GM-106: Explicit EULA acceptance required")
 settings.SERVERS.mkdir(parents=True,exist_ok=True); d=settings.SERVERS/name; d.mkdir(mode=0o750,exist_ok=False)
 item={"id":str(uuid.uuid4()),"name":name,"edition":edition,"software":software,"version":version,"java_port":None,"directory":str(d),"eula_accepted":1}
 try:
  with store.connect() as db:
   db.execute("BEGIN IMMEDIATE")
   used={r[0] for r in db.execute("SELECT java_port FROM servers WHERE java_port IS NOT NULL")}
   item["java_port"]=choose_port(25565,"tcp",used)
   db.execute("INSERT INTO servers(id,name,edition,software,version,java_port,directory,eula_accepted) VALUES(:id,:name,:edition,:software,:version,:java_port,:directory,:eula_accepted)",item);db.commit()
  _download(_vanilla(version) if software=="vanilla" else _paper(version),d/"server.jar")
  (d/"eula.txt").write_text("eula=true\n")
  (d/"server.properties").write_text(f"server-port={item['java_port']}\n")
  if edition=="crossplay":
   p=d/"plugins";p.mkdir()
   for project,filename in (("geyser","Geyser-Spigot.jar"),("floodgate","floodgate-spigot.jar")):
    _download(f"https://download.geysermc.org/v2/projects/{project}/versions/latest/builds/latest/downloads/spigot",p/filename)
  return item
 except Exception:
  with store.connect() as db:db.execute("DELETE FROM servers WHERE id=?",(item["id"],))
  shutil.rmtree(d,ignore_errors=True);raise
def _systemctl(action,item):
 if action not in {"start","stop","restart"}:raise ManagerError("GM-109: Invalid action")
 cmd=["/usr/bin/systemctl",action,f"mmanager-mc@{item['name']}.service"]
 if os.geteuid()!=0:cmd=["/usr/bin/sudo","-n",*cmd]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
 if p.returncode:raise ManagerError("GM-220: "+(p.stderr.strip() or p.stdout.strip())[:300])
def server_action(sid,action):
 item=store.get_server(sid)
 if not item:raise ManagerError("GM-108: Server not found")
 _systemctl(action,item);return {"ok":True,"action":action}
def server_logs(sid,lines=100):
 item=store.get_server(sid)
 if not item:raise ManagerError("GM-108: Server not found")
 if not 1<=lines<=500:raise ManagerError("GM-110: Invalid line count")
 cmd=["/usr/bin/journalctl","-u",f"mmanager-mc@{item['name']}.service","-n",str(lines),"--no-pager","-o","cat"]
 if os.geteuid()!=0:cmd=["/usr/bin/sudo","-n",*cmd]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
 if p.returncode:raise ManagerError("GM-221: Cannot read logs")
 return p.stdout[-50000:]
def create_backup(sid):
 item=store.get_server(sid)
 if not item:raise ManagerError("GM-108: Server not found")
 settings.BACKUPS.mkdir(parents=True,exist_ok=True);bid=str(uuid.uuid4());dest=settings.BACKUPS/f"{item['name']}-{bid}.tar.gz";root=Path(item["directory"]).resolve()
 with tarfile.open(dest,"w:gz") as tar:
  for p in root.rglob("*"):
   if not p.is_symlink():tar.add(p,arcname=p.relative_to(root),recursive=False)
 store.add_backup({"id":bid,"server_id":sid,"filename":str(dest),"size":dest.stat().st_size})
 return {"id":bid,"filename":dest.name,"size":dest.stat().st_size}
def list_backups(sid):
 if not store.get_server(sid):raise ManagerError("GM-108: Server not found")
 return store.list_backups(sid)
def restore_backup(sid,bid,confirm=False):
 if not confirm:raise ManagerError("GM-230: Explicit confirmation required")
 item=store.get_server(sid)
 if not item:raise ManagerError("GM-108: Server not found")
 b=next((x for x in store.list_backups(sid) if x["id"]==bid),None)
 if not b:raise ManagerError("GM-231: Backup not found")
 _systemctl("stop",item);create_backup(sid)
 root=Path(item["directory"]).resolve();stage=root.parent/(root.name+".restore-"+secrets.token_hex(4));stage.mkdir()
 try:
  with tarfile.open(b["filename"],"r:gz") as tar:
   members=tar.getmembers()
   for m in members:
    target=(stage/m.name).resolve()
    if not target.is_relative_to(stage.resolve()) or not (m.isfile() or m.isdir()):raise ManagerError("GM-232: Unsafe archive member rejected")
   for m in members:tar.extract(m,stage,set_attrs=False)
  old=root.parent/(root.name+".old-"+secrets.token_hex(4));root.rename(old);stage.rename(root);shutil.rmtree(old,ignore_errors=True)
 except Exception:shutil.rmtree(stage,ignore_errors=True);raise
 return {"restored":True}
