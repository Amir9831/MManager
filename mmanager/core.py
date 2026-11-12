import json,re,secrets,shutil,subprocess,tarfile,urllib.request,uuid,os,zipfile
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

def _bedrock(version):
 registry=_json("https://raw.githubusercontent.com/EndstoneMC/bedrock-server-data/v2/versions.json")
 release=registry.get("release",{})
 if version=="latest": version=release.get("latest")
 if version not in release.get("versions",[]): raise ManagerError("GM-216: Bedrock release version not found")
 metadata=_json("https://raw.githubusercontent.com/EndstoneMC/bedrock-server-data/v2/release/"+version+"/metadata.json")
 linux=metadata.get("binary",{}).get("linux",{})
 if not linux.get("url"): raise ManagerError("GM-216: Bedrock Linux artifact unavailable")
 return {"url":linux["url"],"checksum":linux.get("sha256"),"algorithm":"sha256"}

def available_versions(edition):
 if edition not in {"java","bedrock","crossplay"}: raise ManagerError("GM-102: Invalid edition")
 if edition=="bedrock":
  registry=_json("https://raw.githubusercontent.com/EndstoneMC/bedrock-server-data/v2/versions.json")
  release=registry.get("release",{})
  return {"latest":release.get("latest"),"versions":[{"id":v,"type":"release"} for v in release.get("versions",[])]}
 manifest=_json("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json")
 versions=[v for v in manifest.get("versions",[]) if v.get("type")=="release"]
 if edition=="crossplay":
  paper=_json("https://fill.papermc.io/v3/projects/paper")
  supported={v for group in paper.get("versions",{}).values() for v in group}
  versions=[v for v in versions if v["id"] in supported]
 return {"latest":manifest.get("latest",{}).get("release"),"versions":[{"id":v["id"],"type":v["type"]} for v in versions]}

def server_settings(sid):
 item=store.get_server(sid)
 if not item: raise ManagerError("GM-108: Server not found")
 path=Path(item["directory"])/"server.properties"; values={}
 if path.exists():
  for line in path.read_text(errors="replace").splitlines():
   if line and not line.lstrip().startswith("#") and "=" in line:
    k,v=line.split("=",1); values[k.strip()]=v.strip()
 return {"settings":values,"edition":item["edition"],"software":item["software"],"version":item["version"]}

def update_server_settings(sid,changes):
 item=store.get_server(sid)
 if not item: raise ManagerError("GM-108: Server not found")
 for k,v in changes.items():
  if not re.fullmatch(r"[a-z0-9_.-]{1,64}",k) or not re.fullmatch(r"[A-Za-z0-9_. -]{0,512}",str(v)): raise ManagerError("GM-240: Invalid server property: "+str(k))
 path=Path(item["directory"])/"server.properties"; current=server_settings(sid)["settings"]
 current.update({k:str(v) for k,v in changes.items()})
 tmp=path.with_suffix(".properties.tmp")
 tmp.write_text("# MManager server configuration\n"+"".join(k+"="+v+"\n" for k,v in sorted(current.items())))
 tmp.replace(path)
 return {"saved":True,"restart_required":True,"settings":current}

def _paper(version):
 url=f"https://fill.papermc.io/v3/projects/paper/versions/{version}/builds"
 req=urllib.request.Request(url,headers={"User-Agent":"MManager/0.2 (https://github.com/Amir9831/MManager)"})
 with urllib.request.urlopen(req,timeout=25) as r: builds=json.load(r)
 if not isinstance(builds,list):raise ManagerError("GM-214: Invalid Paper build metadata")
 stable=next((b for b in builds if b.get("channel")=="STABLE"),None)
 if not stable:raise ManagerError("GM-214: No stable Paper builds for this version")
 download=stable.get("downloads",{}).get("server:default",{})
 if not download.get("url"):raise ManagerError("GM-214: Paper stable build has no server download")
 return {"url":download["url"],"checksum":download.get("checksums",{}).get("sha256"),"algorithm":"sha256"}
def create_server(name,edition="java",version="1.21.4",software="vanilla",accept_eula=False):
 if not NAME.fullmatch(name):raise ManagerError("GM-101: Invalid server name")
 if edition not in {"java","bedrock","crossplay"}:raise ManagerError("GM-102: Invalid edition")
 if software not in {"vanilla","paper","bedrock"} or (edition=="crossplay" and software!="paper") or (edition=="bedrock" and software!="bedrock") or (edition!="bedrock" and software=="bedrock"):raise ManagerError("GM-103: Invalid software for selected edition")
 if not re.fullmatch(r"[A-Za-z0-9._-]{1,40}",version):raise ManagerError("GM-105: Invalid Minecraft version")
 if accept_eula is not True:raise ManagerError("GM-106: Explicit EULA acceptance required")
 settings.SERVERS.mkdir(parents=True,exist_ok=True);d=settings.SERVERS/name;d.mkdir(mode=0o750,exist_ok=False)
 item={"id":str(uuid.uuid4()),"name":name,"edition":edition,"software":software,"version":version,"java_port":None,"bedrock_port":None,"directory":str(d),"eula_accepted":1}
 try:
  with store.connect() as db:
   db.execute("BEGIN IMMEDIATE")
   used_tcp={r[0] for r in db.execute("SELECT java_port FROM servers WHERE java_port IS NOT NULL")}
   item["java_port"]=choose_port(19132 if edition=="bedrock" else 25565,"udp" if edition=="bedrock" else "tcp",used_tcp)
   if edition=="crossplay":
    used_udp={r[0] for r in db.execute("SELECT bedrock_port FROM servers WHERE bedrock_port IS NOT NULL")}
    item["bedrock_port"]=choose_port(19132,"udp",used_udp)
   db.execute("INSERT INTO servers(id,name,edition,software,version,java_port,bedrock_port,directory,eula_accepted) VALUES(:id,:name,:edition,:software,:version,:java_port,:bedrock_port,:directory,:eula_accepted)",item);db.commit()
  artifact=_bedrock(version) if edition=="bedrock" else (_vanilla(version) if software=="vanilla" else _paper(version))
  archive=d/("bedrock.zip" if edition=="bedrock" else "server.jar")
  _download(artifact["url"],archive,artifact.get("checksum"),artifact.get("algorithm","sha256"))
  if edition=="bedrock":
   with zipfile.ZipFile(archive) as zf:
    for member in zf.infolist():
     if not (d/member.filename).resolve().is_relative_to(d.resolve()): raise ManagerError("GM-232: Unsafe Bedrock archive member")
    zf.extractall(d)
   archive.unlink(missing_ok=True)
   binary=d/"bedrock_server"
   if not binary.exists(): raise ManagerError("GM-217: Bedrock binary missing from official archive")
   binary.chmod(0o750)
   (d/"server.properties").write_text("server-port=19132\nserver-portv6=19133\n")
   (d/"run.sh").write_text("#!/bin/sh\ncd /var/lib/mmanager/servers/"+name+"\nLD_LIBRARY_PATH=. exec ./bedrock_server\n")
  else:
   (d/"eula.txt").write_text("eula=true\n")
   (d/"server.properties").write_text(f"server-port={item['java_port']}\n")
   (d/"run.sh").write_text("#!/bin/sh\ncd /var/lib/mmanager/servers/"+name+"\nexec /usr/bin/java -Xms256M -Xmx1G -jar server.jar nogui\n")
  (d/"run.sh").chmod(0o750)
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
 cmd=["/usr/bin/systemctl","is-active",f"mmanager-mc@{item['name']}.service"]
 if os.geteuid()!=0:cmd=["/usr/bin/sudo","-n",*cmd]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=15)
 if p.returncode==0:return True
 if p.returncode==3 and p.stdout.strip()=="inactive":return False
 raise ManagerError("GM-222: Cannot safely determine server state: "+(p.stderr.strip() or p.stdout.strip())[:250])
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
 root=Path(item["directory"]).resolve();stage=root.parent/(root.name+".restore-"+secrets.token_hex(4));old=root.parent/(root.name+".old-"+secrets.token_hex(4));stage.mkdir()
 try:
  with tarfile.open(b["filename"],"r:gz") as tar:
   members=tar.getmembers()
   required=sum(m.size for m in members if m.isfile())
   if required>shutil.disk_usage(stage.parent).free*0.8:raise ManagerError("GM-233: Not enough free disk space for restore")
   for m in members:
    if not (stage/m.name).resolve().is_relative_to(stage.resolve()) or not (m.isfile() or m.isdir()):raise ManagerError("GM-232: Unsafe archive member rejected")
   for m in members:tar.extract(m,stage,set_attrs=False)
  root.rename(old)
  try:stage.rename(root)
  except Exception:
   old.rename(root);raise
  shutil.rmtree(old,ignore_errors=True)
 except Exception:
  shutil.rmtree(stage,ignore_errors=True)
  if old.exists() and not root.exists():old.rename(root)
  raise
 return {"restored":True}


def server_status(sid):
    item = store.get_server(sid)
    if not item:
        raise ManagerError("GM-108: Server not found")
    try:
        active = _active(item)
    except ManagerError as exc:
        return {"status": "unknown", "error": str(exc)}
    return {"status": "running" if active else "stopped"}
