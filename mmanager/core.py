import json,re,secrets,shutil,subprocess,tarfile,urllib.request,uuid,os
from pathlib import Path
from . import store,settings
from .ports import choose_port
NAME=re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,31}$")
class ManagerError(Exception):pass
def _json(url):
 req=urllib.request.Request(url,headers={"User-Agent":"MManager/0.2"})
 with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)
def _download(url,dest,expected=None,algorithm="sha256"):
 tmp=Path(str(dest)+".part");total=0;digest=__import__("hashlib").new(algorithm)
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"MManager/0.2 (https://github.com/Amir9831/MManager)"})
  with urllib.request.urlopen(req,timeout=60) as r,tmp.open("wb") as out:
   while True:
    chunk=r.read(1024*1024)
    if not chunk:break
    total+=len(chunk)
    if total>1024**3:raise ManagerError("GM-210: Download exceeds 1 GiB")
    digest.update(chunk);out.write(chunk)
  if total<1024:raise ManagerError("GM-211: Download unexpectedly small")
  if expected and digest.hexdigest().lower()!=expected.lower():raise ManagerError("GM-215: Download checksum mismatch; refusing to install")
  tmp.replace(dest)
 finally:
  if tmp.exists():tmp.unlink()
def _vanilla(version):
 m=_json("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json")
 v=next((x for x in m["versions"] if x["id"]==version and x["type"] in ("release","snapshot")),None)
 if not v:raise ManagerError("GM-212: Minecraft version not found")
 server=_json(v["url"]).get("downloads",{}).get("server")
 if not server or not server.get("url"):raise ManagerError("GM-213: No server jar for this version")
 return {"url":server["url"],"checksum":server.get("sha1"),"algorithm":"sha1"}
def _paper(version):
 url=f"https://fill.papermc.io/v3/projects/paper/versions/{version}/builds?channel=STABLE"
 req=urllib.request.Request(url,headers={"User-Agent":"MManager/0.2 (https://github.com/Amir9831/MManager)"})
 with urllib.request.urlopen(req,timeout=25) as r: builds=json.load(r)
 if not isinstance(builds,list) or not builds:raise ManagerError("GM-214: No stable Paper builds for this version")
 download=builds[0].get("downloads",{}).get("server:default",{})
 if not download.get("url"):raise ManagerError("GM-214: Paper stable build has no server download")
 return {"url":download["url"],"checksum":download.get("checksums",{}).get("sha256"),"algorithm":"sha256"}
def create_server(name,edition="java",version="1.21.4",software="vanilla",accept_eula=False):
 if not NAME.fullmatch(name):raise ManagerError("GM-101: Invalid server name")
 if edition not in {"java","crossplay"}:raise ManagerError("GM-102: Bedrock-only is not supported in this release")
 if software not in {"vanilla","paper"} or (edition=="crossplay" and software!="paper"):raise ManagerError("GM-103: Crossplay requires Paper")
 if not re.fullmatch(r"[A-Za-z0-9._-]{1,40}",version):raise ManagerError("GM-105: Invalid Minecraft version")
 if accept_eula is not True:raise ManagerError("GM-106: Explicit EULA acceptance required")
 settings.SERVERS.mkdir(parents=True,exist_ok=True);d=settings.SERVERS/name;d.mkdir(mode=0o750,exist_ok=False)
 item={"id":str(uuid.uuid4()),"name":name,"edition":edition,"software":software,"version":version,"java_port":None,"bedrock_port":None,"directory":str(d),"eula_accepted":1}
 try:
  with store.connect() as db:
   db.execute("BEGIN IMMEDIATE")
   used_tcp={r[0] for r in db.execute("SELECT java_port FROM servers WHERE java_port IS NOT NULL")}
   item["java_port"]=choose_port(25565,"tcp",used_tcp)
   if edition=="crossplay":
    used_udp={r[0] for r in db.execute("SELECT bedrock_port FROM servers WHERE bedrock_port IS NOT NULL")}
    item["bedrock_port"]=choose_port(19132,"udp",used_udp)
   db.execute("INSERT INTO servers(id,name,edition,software,version,java_port,bedrock_port,directory,eula_accepted) VALUES(:id,:name,:edition,:software,:version,:java_port,:bedrock_port,:directory,:eula_accepted)",item);db.commit()
  artifact=_vanilla(version) if software=="vanilla" else _paper(version)
  _download(artifact["url"],d/"server.jar",artifact.get("checksum"),artifact.get("algorithm","sha256"))
  (d/"eula.txt").write_text("eula=true\n")
  (d/"server.properties").write_text(f"server-port={item['java_port']}\n")
  if edition=="crossplay":
   plugins=d/"plugins";plugins.mkdir()
   for project,filename in (("geyser","Geyser-Spigot.jar"),("floodgate","floodgate-spigot.jar")):
    _download(f"https://download.geysermc.org/v2/projects/{project}/versions/latest/builds/latest/downloads/spigot",plugins/filename)
   geyser=plugins/"Geyser-Spigot";geyser.mkdir(exist_ok=True)
   (geyser/"config.yml").write_text("bedrock:\n  address: 0.0.0.0\n  port: "+str(item["bedrock_port"])+"\n  clone-remote-port: false\nremote:\n  address: auto\n  port: "+str(item["java_port"])+"\n  auth-type: floodgate\n")
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
def _active(item):
 cmd=["/usr/bin/systemctl","is-active","--quiet",f"mmanager-mc@{item['name']}.service"]
 if os.geteuid()!=0:cmd=["/usr/bin/sudo","-n",*cmd]
 return subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15).returncode==0
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
 was_active=_active(item)
 if was_active:_systemctl("stop",item)
 settings.BACKUPS.mkdir(parents=True,exist_ok=True);bid=str(uuid.uuid4());dest=settings.BACKUPS/f"{item['name']}-{bid}.tar.gz";root=Path(item["directory"]).resolve()
 try:
  with tarfile.open(dest,"w:gz") as tar:
   for p in root.rglob("*"):
    if not p.is_symlink():tar.add(p,arcname=p.relative_to(root),recursive=False)
  store.add_backup({"id":bid,"server_id":sid,"filename":str(dest),"size":dest.stat().st_size})
  return {"id":bid,"filename":dest.name,"size":dest.stat().st_size}
 except Exception:
  dest.unlink(missing_ok=True);raise
 finally:
  if was_active:_systemctl("start",item)
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
    if not (stage/m.name).resolve().is_relative_to(stage.resolve()) or not (m.isfile() or m.isdir()):raise ManagerError("GM-232: Unsafe archive member rejected")
   for m in members:tar.extract(m,stage,set_attrs=False)
  old=root.parent/(root.name+".old-"+secrets.token_hex(4));root.rename(old);stage.rename(root);shutil.rmtree(old,ignore_errors=True)
 except Exception:shutil.rmtree(stage,ignore_errors=True);raise
 return {"restored":True}
