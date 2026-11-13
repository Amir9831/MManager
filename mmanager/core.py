import json,re,secrets,shutil,subprocess,tarfile,urllib.request,uuid,os,zipfile,stat
import yaml
from collections import deque
from pathlib import Path
from . import store,settings
from .ports import choose_port
from . import networking
NAME=re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,31}$")
SERVER_LOG_DIR=Path(os.environ.get("MMANAGER_LOG_DIR","/var/log/mmanager/servers"))
BEDROCK_NETHERNET_MIN_VERSION=(1,26,60)
BEDROCK_UDP_PORT_RANGE="49152-49200"
class ManagerError(Exception):pass

def _bedrock_uses_nethernet(version):
 match=re.match(r"^(\d+)\.(\d+)\.(\d+)",str(version))
 return bool(match and tuple(map(int,match.groups()))>=BEDROCK_NETHERNET_MIN_VERSION)

def _bedrock_port_protocol(version):
 return "tcp" if _bedrock_uses_nethernet(version) else "udp"

def _allocate_bedrock_ipv6_port(game_port, reserved):
 reserved=set(reserved or ()) | {int(game_port)}
 candidate=choose_port(19133,"udp",reserved)
 if candidate in reserved:
  candidate=int(game_port)+1 if int(game_port)<65535 else int(game_port)-1
 if not 1024<=int(candidate)<=65535 or int(candidate) in reserved:
  raise ManagerError("GM-261: Cannot allocate a distinct IPv6 Bedrock UDP port")
 return int(candidate)
def _json(url):
 req=urllib.request.Request(url,headers={"User-Agent":"MManager/0.2"})
 with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)
def _download(url,dest,expected=None,algorithm="sha256"):
 tmp=Path(str(dest)+".part");total=0;digest=__import__("hashlib").new(algorithm)
 try:
  ua="Mozilla/5.0" if "minecraft.net/" in url else "MManager/0.2 (https://github.com/Amir9831/MManager)"
  req=urllib.request.Request(url,headers={"User-Agent":ua})
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
 template=Path(__file__).parent/"templates"/("bedrock-server.properties" if item["edition"]=="bedrock" else "java-server.properties")
 if template.exists():
  for line in template.read_text().splitlines():
   if line and not line.lstrip().startswith("#") and "=" in line:
    k,v=line.split("=",1); values[k.strip()]=v.strip()
 if path.exists():
  for line in path.read_text(errors="replace").splitlines():
   if line and not line.lstrip().startswith("#") and "=" in line:
    k,v=line.split("=",1); values[k.strip()]=v.strip()
 return {"settings":values,"edition":item["edition"],"software":item["software"],"version":item["version"]}

def update_server_network(sid, ipv4_enabled, ipv6_enabled):
    item = store.get_server(sid)
    if not item:
        raise ManagerError("GM-108: Server not found")
    if type(ipv4_enabled) is not bool or type(ipv6_enabled) is not bool or not (ipv4_enabled or ipv6_enabled):
        raise ManagerError("GM-260: Enable IPv4, IPv6, or both; both cannot be disabled")
    was_active = _active(item)
    old4, old6 = bool(item.get("ipv4_enabled", 1)), bool(item.get("ipv6_enabled", 0))
    store.update_server_network(sid, ipv4_enabled, ipv6_enabled)
    updated = store.get_server(sid)
    root = Path(updated["directory"])
    try:
        if updated["edition"] == "bedrock":
            _configure_bedrock_properties(root / "server.properties", updated["java_port"], updated["version"],
                                          ipv4_enabled, ipv6_enabled, updated.get("ipv6_port"))
        else:
            _configure_java_properties(root / "server.properties", updated["java_port"], ipv4_enabled, ipv6_enabled)
            if updated["edition"] == "crossplay":
                _configure_geyser(root / "plugins" / "Geyser-Spigot" / "config.yml",
                                  updated["bedrock_port"], updated["java_port"], ipv4_enabled, ipv6_enabled)
        networking.apply(updated)
        if was_active:
            _systemctl("restart", updated)
    except Exception:
        store.update_server_network(sid, old4, old6)
        previous = store.get_server(sid)
        try:
            if previous["edition"] == "bedrock":
                _configure_bedrock_properties(root / "server.properties", previous["java_port"], previous["version"],
                                              old4, old6, previous.get("ipv6_port"))
            else:
                _configure_java_properties(root / "server.properties", previous["java_port"], old4, old6)
                if previous["edition"] == "crossplay":
                    _configure_geyser(root / "plugins" / "Geyser-Spigot" / "config.yml",
                                      previous["bedrock_port"], previous["java_port"], old4, old6)
            networking.apply(previous)
        except Exception:
            pass
        raise
    return {"saved": True, "ipv4_enabled": ipv4_enabled, "ipv6_enabled": ipv6_enabled,
            "ipv6_port": updated.get("ipv6_port"), "restarted": was_active}


def update_server_settings(sid,changes):
 item=store.get_server(sid)
 if not item: raise ManagerError("GM-108: Server not found")
 for k,v in changes.items():
  if not re.fullmatch(r"[a-z0-9_.-]{1,64}",k) or not re.fullmatch(r"[^\r\n]{0,512}",str(v)): raise ManagerError("GM-240: Invalid server property: "+str(k))
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
 item={"id":str(uuid.uuid4()),"name":name,"edition":edition,"software":software,"version":version,"java_port":None,"bedrock_port":None,"ipv6_port":None,"ipv4_enabled":1,"ipv6_enabled":0,"directory":str(d),"eula_accepted":1}
 try:
  with store.connect() as db:
   db.execute("BEGIN IMMEDIATE")
   used_tcp=set()
   used_udp={r[0] for r in db.execute("SELECT bedrock_port FROM servers WHERE bedrock_port IS NOT NULL")}
   for row in db.execute("SELECT edition,version,java_port FROM servers WHERE java_port IS NOT NULL"):
    if row["edition"]=="bedrock" and _bedrock_port_protocol(row["version"])=="udp":
     used_udp.add(row["java_port"])
    else:
     used_tcp.add(row["java_port"])
   if edition=="bedrock":
    protocol=_bedrock_port_protocol(version)
    item["java_port"]=choose_port(19132,protocol,used_tcp if protocol=="tcp" else used_udp)
    item["ipv6_port"]=_allocate_bedrock_ipv6_port(item["java_port"],used_udp)
   else:
    item["java_port"]=choose_port(25565,"tcp",used_tcp)
   if edition=="crossplay":
    item["bedrock_port"]=choose_port(19132,"udp",used_udp)
   db.execute("INSERT INTO servers(id,name,edition,software,version,java_port,bedrock_port,ipv6_port,ipv4_enabled,ipv6_enabled,directory,eula_accepted) VALUES(:id,:name,:edition,:software,:version,:java_port,:bedrock_port,:ipv6_port,:ipv4_enabled,:ipv6_enabled,:directory,:eula_accepted)",item);db.commit()
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
   props=(Path(__file__).parent/"templates"/"bedrock-server.properties").read_text()
   (d/"server.properties").write_text(props)
   _configure_bedrock_properties(d/"server.properties",item["java_port"],version,item.get("ipv4_enabled",1),item.get("ipv6_enabled",0),item.get("ipv6_port"))
   (d/"run.sh").write_text("#!/bin/sh\ncd /var/lib/mmanager/servers/"+name+"\nLD_LIBRARY_PATH=. exec ./bedrock_server\n")
  else:
   (d/"eula.txt").write_text("eula=true\n")
   props=(Path(__file__).parent/"templates"/"java-server.properties").read_text()
   (d/"server.properties").write_text(props)
   _configure_java_properties(d/"server.properties",item["java_port"],item.get("ipv4_enabled",1),item.get("ipv6_enabled",0))
   (d/"run.sh").write_text("#!/bin/sh\ncd /var/lib/mmanager/servers/"+name+"\nexec /usr/bin/java -Xms256M -Xmx1G -jar server.jar nogui\n")
  (d/"run.sh").chmod(0o750)
  if edition=="crossplay":
   plugins=d/"plugins";plugins.mkdir()
   for project,filename in (("geyser","Geyser-Spigot.jar"),("floodgate","floodgate-spigot.jar")):
    _download(f"https://download.geysermc.org/v2/projects/{project}/versions/latest/builds/latest/downloads/spigot",plugins/filename)
   geyser=plugins/"Geyser-Spigot";geyser.mkdir(exist_ok=True)
   geyser_config=geyser/"config.yml"
   shutil.copy2(Path(__file__).parent/"templates"/"crossplay-geyser.yml", geyser_config)
   _configure_geyser(geyser_config, item["bedrock_port"], item["java_port"],item.get("ipv4_enabled",1),item.get("ipv6_enabled",0))
  return item
 except Exception:
  with store.connect() as db:db.execute("DELETE FROM servers WHERE id=?",(item["id"],))
  shutil.rmtree(d,ignore_errors=True);raise
def _systemctl(action,item):
 if action not in {"start","stop","restart"}:raise ManagerError("GM-109: Invalid action")
 if action in {"start","restart"}:
  try: networking.apply(item)
  except (OSError,RuntimeError,subprocess.TimeoutExpired) as exc: raise ManagerError("GM-260: "+str(exc)[:300])
 cmd=["/usr/bin/systemctl",action,f"mmanager-mc@{item['name']}.service"]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
 if p.returncode:raise ManagerError("GM-220: "+(p.stderr.strip() or p.stdout.strip())[:300])
def _active(item):
 cmd=["/usr/bin/systemctl","is-active",f"mmanager-mc@{item['name']}.service"]
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=15)
 except (OSError,subprocess.TimeoutExpired) as exc:
  raise ManagerError("GM-222: Cannot determine server state: "+str(exc)[:250])
 if p.returncode==0:return True
 # systemctl uses exit status 3 for a known unit that is not active,
 # including failed/inactive states. A failed server must still be switchable.
 if p.returncode==3:return False
 raise ManagerError("GM-222: Cannot safely determine server state: "+(p.stderr.strip() or p.stdout.strip())[:250])
def server_action(sid,action):
 item=store.get_server(sid)
 if not item:raise ManagerError("GM-108: Server not found")
 # Repair existing Bedrock properties after MManager upgrades before the next launch.
 if action in {"start","restart"}:
  root=Path(item["directory"])
  if item["edition"]=="bedrock":
   _configure_bedrock_properties(root/"server.properties",item["java_port"],item["version"],item.get("ipv4_enabled",1),item.get("ipv6_enabled",0),item.get("ipv6_port"))
  else:
   _configure_java_properties(root/"server.properties",item["java_port"],item.get("ipv4_enabled",1),item.get("ipv6_enabled",0))
   if item["edition"]=="crossplay":
    _configure_geyser(root/"plugins"/"Geyser-Spigot"/"config.yml",item["bedrock_port"],item["java_port"],item.get("ipv4_enabled",1),item.get("ipv6_enabled",0))
 _systemctl(action,item);return {"ok":True,"action":action}
def server_logs(sid,lines=100):
 item=store.get_server(sid)
 if not item:raise ManagerError("GM-108: Server not found")
 if not 1<=lines<=500:raise ManagerError("GM-110: Invalid line count")
 log_path=SERVER_LOG_DIR/(item["name"]+".log")
 tail=deque(maxlen=lines)
 try:
  with log_path.open("r",errors="replace") as stream:
   for row in stream:tail.append(row)
 except FileNotFoundError:
  return ""
 except OSError as exc:
  raise ManagerError("GM-221: Cannot read logs: "+str(exc)[:250])
 return "".join(tail)[-50000:]

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
def import_backup(sid, fileobj, original_filename):
 item=store.get_server(sid)
 if not item:raise ManagerError("GM-108: Server not found")
 name=Path(str(original_filename or "")).name.lower()
 if not (name.endswith(".tar.gz") or name.endswith(".tgz")):raise ManagerError("GM-234: Backup must be a .tar.gz or .tgz archive")
 settings.BACKUPS.mkdir(parents=True,exist_ok=True)
 bid=str(uuid.uuid4());dest=settings.BACKUPS/f"{item['name']}-import-{bid}.tar.gz"
 total=0
 try:
  with dest.open("xb") as out:
   while True:
    chunk=fileobj.read(1024*1024)
    if not chunk:break
    total+=len(chunk)
    if total>8*1024**3:raise ManagerError("GM-235: Uploaded backup exceeds 8 GiB")
    out.write(chunk)
  if total<32:raise ManagerError("GM-234: Backup archive is empty or invalid")
  with tarfile.open(dest,"r:gz") as tar:
   members=tar.getmembers()
   if not members:raise ManagerError("GM-234: Backup archive is empty")
   root_files={Path(m.name).parts[0] for m in members if Path(m.name).parts}
   if "server.properties" not in root_files or not ({"server.jar","bedrock_server"} & root_files):
    raise ManagerError("GM-234: Archive is not a valid MManager Minecraft server backup")
   expanded=0
   for member in members:
    target=(Path("/safe-root")/member.name).resolve()
    if Path(member.name).is_absolute() or ".." in Path(member.name).parts or not target.is_relative_to(Path("/safe-root")) or not (member.isfile() or member.isdir()):
     raise ManagerError("GM-232: Unsafe backup archive member rejected")
    expanded+=member.size
    if expanded>16*1024**3:raise ManagerError("GM-235: Expanded backup exceeds 16 GiB")
  store.add_backup({"id":bid,"server_id":sid,"filename":str(dest),"size":dest.stat().st_size})
  return {"id":bid,"filename":dest.name,"size":dest.stat().st_size,"imported":True}
 except Exception:
  dest.unlink(missing_ok=True)
  raise

def list_backups(sid):
 if not store.get_server(sid):raise ManagerError("GM-108: Server not found")
 return store.list_backups(sid)

def backup_file(sid,bid):
 if not store.get_server(sid):raise ManagerError("GM-108: Server not found")
 backup=store.get_backup(sid,bid)
 if not backup:raise ManagerError("GM-231: Backup not found")
 root=settings.BACKUPS.resolve()
 path=Path(backup["filename"]).resolve()
 if not path.is_relative_to(root) or not path.is_file():
  raise ManagerError("GM-236: Backup file is missing or outside the backup directory")
 return path

def delete_backup(sid,bid):
 path=backup_file(sid,bid)
 path.unlink()
 if not store.delete_backup(sid,bid):
  raise ManagerError("GM-231: Backup record disappeared during deletion")
 return {"deleted":True,"id":bid}
def restore_backup(sid,bid,confirm=False):
 if not confirm:raise ManagerError("GM-230: Explicit confirmation required")
 item=store.get_server(sid)
 if not item:raise ManagerError("GM-108: Server not found")
 b=next((x for x in store.list_backups(sid) if x["id"]==bid),None)
 if not b:raise ManagerError("GM-231: Backup not found")
 was_active=_active(item)
 root=Path(item["directory"]).resolve()
 stage=root.parent/(root.name+".restore-"+secrets.token_hex(4))
 old=root.parent/(root.name+".old-"+secrets.token_hex(4))
 try:
  if was_active:_systemctl("stop",item)
  create_backup(sid)
  stage.mkdir()
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
  return {"restored":True,"restarted":was_active}
 except Exception:
  shutil.rmtree(stage,ignore_errors=True)
  if old.exists() and not root.exists():old.rename(root)
  raise
 finally:
  if was_active and root.exists():_systemctl("start",item)

def update_server(sid, version):
    """Install a verified game-server release with a full pre-update backup."""
    item=store.get_server(sid)
    if not item: raise ManagerError("GM-108: Server not found")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,40}",str(version)): raise ManagerError("GM-105: Invalid Minecraft version")
    if version==item["version"] and item["software"]!="paper": raise ManagerError("Requested version is already installed.")
    if item["edition"]=="bedrock": artifact=_bedrock(version)
    elif item["software"]=="vanilla": artifact=_vanilla(version)
    else: artifact=_paper(version)
    was_active=_active(item)
    if was_active: _systemctl("stop",item)
    backup=None
    root=Path(item["directory"]).resolve()
    try:
        backup=create_backup(sid)
        import tempfile
        settings.ROOT.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="mmanager-update-",dir=settings.ROOT) as tmpname:
            tmp=Path(tmpname)
            if item["edition"]=="bedrock":
                archive=tmp/"bedrock.zip"
                _download(artifact["url"],archive,artifact.get("checksum"),artifact.get("algorithm","sha256"))
                unpack=tmp/"unpack"; unpack.mkdir()
                with zipfile.ZipFile(archive) as zf:
                    for member in zf.infolist():
                        if not (unpack/member.filename).resolve().is_relative_to(unpack.resolve()):
                            raise ManagerError("GM-232: Unsafe Bedrock archive member")
                    zf.extractall(unpack)
                stage=tmp/"stage"
                shutil.copytree(root,stage,symlinks=False)
                preserve={"worlds","world_templates","server.properties","allowlist.json","permissions.json","valid_known_packs.json"}
                for src in unpack.rglob("*"):
                    rel=src.relative_to(unpack)
                    if rel.parts and rel.parts[0] in preserve: continue
                    if src.is_dir():
                        (stage/rel).mkdir(parents=True,exist_ok=True)
                    elif src.is_file():
                        target=stage/rel; target.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(src,target)
                binary=stage/"bedrock_server"
                if not binary.is_file(): raise ManagerError("GM-217: Updated Bedrock archive has no server binary")
                binary.chmod(0o750)
            else:
                downloaded=tmp/"server.jar"
                _download(artifact["url"],downloaded,artifact.get("checksum"),artifact.get("algorithm","sha1" if item["software"]=="vanilla" else "sha256"))
                stage=tmp/"stage"
                shutil.copytree(root,stage,symlinks=False)
                shutil.copy2(downloaded,stage/"server.jar")
            # Reapply MManager-owned listener settings after replacing the runtime.
            # This repairs stale/default ports while preserving unrelated user settings.
            if item["edition"] == "bedrock":
                _configure_bedrock_properties(stage / "server.properties", item["java_port"], version,item.get("ipv4_enabled",1),item.get("ipv6_enabled",0),item.get("ipv6_port"))
            else:
                _configure_java_properties(stage / "server.properties", item["java_port"],item.get("ipv4_enabled",1),item.get("ipv6_enabled",0))
            if item["edition"] == "crossplay":
                geyser_config = stage / "plugins" / "Geyser-Spigot" / "config.yml"
                if not geyser_config.is_file():
                    raise ManagerError("GM-237: Cross-play update is missing the Geyser config.yml")
                _configure_geyser(geyser_config, item["bedrock_port"], item["java_port"],item.get("ipv4_enabled",1),item.get("ipv6_enabled",0))
            state={"backup_id":backup["id"],"previous_version":item["version"],"updated_version":version}
            (stage/"mmanager-update-state.json").write_text(json.dumps(state))
            old=root.parent/(root.name+".update-old-"+secrets.token_hex(4))
            root.rename(old)
            try: stage.rename(root)
            except Exception:
                old.rename(root); raise
            shutil.rmtree(old,ignore_errors=True)
        store.update_server_version(sid,version)
        if was_active: _systemctl("start",item)
        return {"updated":True,"from":item["version"],"to":version,"backup_id":backup["id"],"restart_required":False}
    except Exception:
        if backup:
            try:
                restore_backup(sid,backup["id"],True)
                store.update_server_version(sid,item["version"])
            except Exception as rollback_error:
                raise ManagerError("Update failed and automatic rollback also failed: "+str(rollback_error))
        if was_active:
            try: _systemctl("start",item)
            except Exception: pass
        raise

def rollback_server(sid):
    item=store.get_server(sid)
    if not item: raise ManagerError("GM-108: Server not found")
    state_path=Path(item["directory"])/"mmanager-update-state.json"
    if not state_path.is_file(): raise ManagerError("No successful server update is available to roll back.")
    try: state=json.loads(state_path.read_text())
    except (OSError,ValueError): raise ManagerError("Update rollback metadata is invalid.")
    backup_id=state.get("backup_id"); previous=state.get("previous_version")
    if not backup_id or not previous: raise ManagerError("Update rollback metadata is incomplete.")
    restore_backup(sid,backup_id,True)
    store.update_server_version(sid,previous)
    return {"rolled_back":True,"version":previous,"restored_backup":backup_id}

def _safe_extract_bedrock(archive, destination):
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            name = member.filename.replace("\\\\", "/")
            parts = Path(name).parts
            mode = (member.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(mode)
            if name.startswith("/") or ".." in parts or (parts and ":" in parts[0]):
                raise ManagerError("GM-232: Unsafe Bedrock archive member")
            if stat.S_ISLNK(mode) or file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ManagerError("GM-232: Unsupported Bedrock archive member type")
        zf.extractall(destination)
    if not (destination / "bedrock_server").is_file():
        raise ManagerError("GM-217: Bedrock archive has no server binary")


def _write_server_runtime(root, edition, software, version, java_port, bedrock_port, ipv4_enabled=True, ipv6_enabled=False, ipv6_port=19133):
    if edition == "bedrock":
        artifact = _bedrock(version)
        archive = root / "bedrock.zip"
        _download(artifact["url"], archive, artifact.get("checksum"), artifact.get("algorithm", "sha256"))
        _safe_extract_bedrock(archive, root)
        archive.unlink(missing_ok=True)
        binary = root / "bedrock_server"
        binary.chmod(0o750)
        props = (Path(__file__).parent / "templates" / "bedrock-server.properties").read_text()
        (root / "server.properties").write_text(props)
        _configure_bedrock_properties(root / "server.properties", java_port, version,ipv4_enabled,ipv6_enabled,ipv6_port)
        (root / "run.sh").write_text("#!/bin/sh\ncd \"$(dirname \"$0\")\"\nLD_LIBRARY_PATH=. exec ./bedrock_server\n")
    else:
        artifact = _vanilla(version) if software == "vanilla" else _paper(version)
        jar = root / "server.jar"
        _download(artifact["url"], jar, artifact.get("checksum"), artifact.get("algorithm", "sha1" if software == "vanilla" else "sha256"))
        if not (root / "server.properties").exists():
            props = (Path(__file__).parent / "templates" / "java-server.properties").read_text()
            (root / "server.properties").write_text(props)
        _configure_java_properties(root / "server.properties", java_port,ipv4_enabled,ipv6_enabled)
        (root / "eula.txt").write_text("eula=true\n")
        (root / "run.sh").write_text("#!/bin/sh\ncd \"$(dirname \"$0\")\"\nexec /usr/bin/java -Xms256M -Xmx1G -jar server.jar nogui\n")
    (root / "run.sh").chmod(0o750)
    if edition == "crossplay":
        plugins = root / "plugins"
        plugins.mkdir(exist_ok=True)
        for project, filename in (("geyser", "Geyser-Spigot.jar"), ("floodgate", "floodgate-spigot.jar")):
            dest = plugins / filename
            if not dest.exists():
                _download("https://download.geysermc.org/v2/projects/" + project + "/versions/latest/builds/latest/downloads/spigot", dest)
        geyser = plugins / "Geyser-Spigot"
        geyser.mkdir(exist_ok=True)
        config_path = geyser / "config.yml"
        config = config_path.read_text() if config_path.exists() else (Path(__file__).parent / "templates" / "crossplay-geyser.yml").read_text()
        config_path.write_text(config)
        _configure_geyser(config_path, bedrock_port, java_port,ipv4_enabled,ipv6_enabled)


def _configure_java_properties(path, port, ipv4_enabled=True, ipv6_enabled=True):
    """Keep Java/Paper listener and optional query listener aligned with the allocated TCP port."""
    for key, value in (
        ("server-ip", _network_bind_address(ipv4_enabled, ipv6_enabled)),
        ("server-port", str(port)),
        ("query.port", str(port)),
        ("enable-query", "false"),
        ("enable-rcon", "false"),
    ):
        _set_property_file(path, key, value)


def _configure_geyser(path, bedrock_port, java_port, ipv4_enabled=True, ipv6_enabled=True):
    """Configure Geyser's Bedrock listener and its local Paper/Floodgate backend."""
    path = Path(path)
    try:
        config = yaml.safe_load(path.read_text()) if path.exists() else {}
    except (OSError, yaml.YAMLError) as exc:
        raise ManagerError("GM-238: Cannot read Geyser configuration: " + str(exc)[:200])
    if not isinstance(config, dict):
        raise ManagerError("GM-238: Geyser configuration must be a YAML mapping")
    bedrock = config.setdefault("bedrock", {})
    remote = config.setdefault("remote", {})
    if not isinstance(bedrock, dict) or not isinstance(remote, dict):
        raise ManagerError("GM-238: Geyser bedrock/remote configuration sections are invalid")
    bedrock.update({"address": _network_bind_address(ipv4_enabled, ipv6_enabled, dual_stack="::"), "port": int(bedrock_port), "clone-remote-port": False, "transport": "nethernet"})
    remote.update({"address": "127.0.0.1", "port": int(java_port), "auth-type": "floodgate"})
    path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))


def _network_bind_address(ipv4_enabled, ipv6_enabled, dual_stack=""):
    if not ipv4_enabled and not ipv6_enabled:
        raise ManagerError("GM-260: At least one IP family must remain enabled")
    if ipv4_enabled and ipv6_enabled:
        return dual_stack
    return "0.0.0.0" if ipv4_enabled else "::"


def _configure_bedrock_properties(path, port, version, ipv4_enabled=True, ipv6_enabled=False, ipv6_port=None):
    """Configure RakNet's separate UDP ports or NetherNet's address/transport settings."""
    if not ipv4_enabled and not ipv6_enabled:
        raise ManagerError("GM-260: At least one IP family must remain enabled")
    for key, value in (
        ("server-port", port),
        ("server-portv6", ipv6_port or 19133),
        ("enable-lan-visibility", "false"),
        ("enable-lan-broadcast", "false"),
    ):
        _set_property_file(path, key, str(value))
    if _bedrock_uses_nethernet(version):
        _set_property_file(path, "transport", "nethernet")
        _set_property_file(path, "server-ip", _network_bind_address(bool(ipv4_enabled), bool(ipv6_enabled)))
        _set_property_file(path, "server-udp-ports", BEDROCK_UDP_PORT_RANGE)
    else:
        _remove_property_file(path, "transport")
        _remove_property_file(path, "server-ip")
        _remove_property_file(path, "server-udp-ports")


def _remove_property_file(path, key):
    path = Path(path)
    if not path.exists():
        return
    rows = path.read_text(errors="replace").splitlines()
    rows = [row for row in rows if not (row and not row.lstrip().startswith("#") and "=" in row and row.split("=", 1)[0].strip() == key)]
    path.write_text("\n".join(rows) + "\n")


def _set_property_file(path, key, value):
    path = Path(path)
    rows = path.read_text(errors="replace").splitlines() if path.exists() else []
    result = []
    found = False
    for row in rows:
        if row and not row.lstrip().startswith("#") and "=" in row and row.split("=", 1)[0].strip() == key:
            if not found:
                result.append(key + "=" + str(value))
                found = True
        else:
            result.append(row)
    if not found:
        result.append(key + "=" + str(value))
    path.write_text("\n".join(result) + "\n")


def switch_server(sid, edition, software, version, confirm_world_reset=False):
    """Switch edition/software transactionally; cross-edition worlds are archived, never silently converted."""
    item = store.get_server(sid)
    if not item:
        raise ManagerError("GM-108: Server not found")
    if edition not in {"java", "bedrock", "crossplay"}:
        raise ManagerError("GM-102: Invalid target edition")
    if software not in {"vanilla", "paper", "bedrock"}:
        raise ManagerError("GM-103: Invalid target software")
    if (edition == "bedrock" and software != "bedrock") or (edition == "crossplay" and software != "paper") or (edition == "java" and software not in {"vanilla", "paper"}):
        raise ManagerError("GM-103: Software does not match target edition")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,40}", str(version)):
        raise ManagerError("GM-105: Invalid Minecraft version")
    cross_edition = (item["edition"] == "bedrock") != (edition == "bedrock")
    if cross_edition and confirm_world_reset is not True:
        raise ManagerError("Switching between Java and Bedrock does not convert worlds. Explicitly confirm that the old world will be archived and a new world created.")
    if item["edition"] == edition and item["software"] == software and item["version"] == version:
        return {"switched": False, "unchanged": True, "edition": edition, "software": software, "version": version}
    if item["edition"] == edition and item["software"] == software:
        result = update_server(sid, version)
        return {"switched": True, "edition": edition, "software": software, "version": version, "update": result}
    if item["edition"] == "bedrock" and edition == "bedrock":
        result = update_server(sid, version)
        return {"switched": True, "edition": edition, "software": software, "version": version, "update": result}

    was_active = _active(item)
    if was_active:
        _systemctl("stop", item)
    root = Path(item["directory"]).resolve()
    stage = root.parent / (root.name + ".switch-stage-" + secrets.token_hex(4))
    archived = root.parent / (root.name + ".archived-" + secrets.token_hex(4))
    backup = None
    try:
        backup = create_backup(sid)
        if cross_edition:
            stage.mkdir()
            _write_server_runtime(stage, edition, software, version,
                                  19132 if edition == "bedrock" else 25565,
                                  19132 if edition == "crossplay" else None)
            # Carry only settings that have equivalent meaning in both editions.
            old_settings = server_settings(sid)["settings"]
            common = {"max-players", "difficulty", "gamemode", "online-mode", "motd"}
            new_values = {k: old_settings[k] for k in common if k in old_settings}
            if edition == "bedrock":
                new_values.pop("motd", None)
                new_values["server-name"] = old_settings.get("server-name", "Bedrock Server")
            else:
                new_values["motd"] = old_settings.get("motd", "A Minecraft Server")
            if new_values:
                for key, value in new_values.items():
                    _set_property_file(stage / "server.properties", key, value)
        else:
            shutil.copytree(root, stage, symlinks=False)
            if edition in {"java", "crossplay"}:
                _write_server_runtime(stage, edition, software, version,
                                      25565, 19132 if edition == "crossplay" else None)
                if item["edition"] == "crossplay" and edition == "java":
                    plugins = stage / "plugins"
                    disabled = stage / ".mmanager-disabled-plugins"
                    disabled.mkdir(exist_ok=True)
                    for filename in ("Geyser-Spigot.jar", "floodgate-spigot.jar"):
                        source = plugins / filename
                        if source.exists():
                            shutil.move(str(source), str(disabled / filename))
            else:
                raise ManagerError("Unsupported edition transition.")
        # Preserve a stable TCP/UDP port allocation in the registry.
        with store.connect() as db:
            used_tcp = set()
            used_udp = {r[0] for r in db.execute(
                "SELECT bedrock_port FROM servers WHERE id<>? AND bedrock_port IS NOT NULL", (sid,))}
            used_udp.update(r[0] for r in db.execute(
                "SELECT ipv6_port FROM servers WHERE id<>? AND ipv6_port IS NOT NULL", (sid,)))
            for row in db.execute(
                "SELECT edition,version,java_port FROM servers WHERE id<>? AND java_port IS NOT NULL", (sid,)):
                if row["edition"] == "bedrock" and _bedrock_port_protocol(row["version"]) == "udp":
                    used_udp.add(row["java_port"])
                else:
                    used_tcp.add(row["java_port"])
        if edition == "bedrock":
            protocol = _bedrock_port_protocol(version)
            java_port = choose_port(19132, protocol, used_tcp if protocol == "tcp" else used_udp)
            ipv6_port = _allocate_bedrock_ipv6_port(java_port, used_udp)
            bedrock_port = None
        else:
            java_port = choose_port(25565, "tcp", used_tcp)
            bedrock_port = choose_port(19132, "udp", used_udp) if edition == "crossplay" else None
            ipv6_port = None
        if edition != "bedrock":
            _configure_java_properties(stage / "server.properties", java_port,item.get("ipv4_enabled",1),item.get("ipv6_enabled",0))
        else:
            _configure_bedrock_properties(stage / "server.properties", java_port, version,item.get("ipv4_enabled",1),item.get("ipv6_enabled",0),ipv6_port)
        if edition == "crossplay":
            geyser_cfg = stage / "plugins" / "Geyser-Spigot" / "config.yml"
            _configure_geyser(geyser_cfg, bedrock_port, java_port,item.get("ipv4_enabled",1),item.get("ipv6_enabled",0))
        # Validate the complete target runtime before touching the live directory.
        required = ["server.properties", "run.sh"]
        required.append("bedrock_server" if edition == "bedrock" else "server.jar")
        missing = [name for name in required if not (stage / name).is_file()]
        if missing:
            raise ManagerError("GM-237: Target runtime is incomplete; missing: " + ", ".join(missing))
        if edition == "crossplay":
            plugins = stage / "plugins"
            for name in ("Geyser-Spigot.jar", "floodgate-spigot.jar"):
                if not (plugins / name).is_file():
                    raise ManagerError("GM-237: Cross-play runtime is incomplete; missing plugins/" + name)
            if not (plugins / "Geyser-Spigot" / "config.yml").is_file():
                raise ManagerError("GM-237: Cross-play runtime is missing Geyser config.yml")
        root.rename(archived)
        try:
            stage.rename(root)
        except Exception:
            archived.rename(root)
            raise
        with store.connect() as db:
            db.execute("UPDATE servers SET edition=?,software=?,version=?,java_port=?,bedrock_port=?,ipv6_port=? WHERE id=?",
                       (edition, software, version, java_port, bedrock_port, ipv6_port, sid))
        if was_active:
            _systemctl("start", store.get_server(sid))
        if not cross_edition:
            shutil.rmtree(archived, ignore_errors=True)
        return {"switched": True, "from": {"edition": item["edition"], "software": item["software"], "version": item["version"]},
                "to": {"edition": edition, "software": software, "version": version}, "backup_id": backup["id"],
                "world_archived": bool(cross_edition), "restarted": was_active}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        if archived.exists():
            failed = root.parent / (root.name + ".switch-failed-" + secrets.token_hex(4))
            if root.exists():
                root.rename(failed)
            archived.rename(root)
            shutil.rmtree(failed, ignore_errors=True)
        with store.connect() as db:
            db.execute("UPDATE servers SET edition=?,software=?,version=?,java_port=?,bedrock_port=?,ipv6_port=? WHERE id=?",
                       (item["edition"], item["software"], item["version"], item["java_port"], item["bedrock_port"], item.get("ipv6_port"), sid))
        if was_active and root.exists():
            try:
                _systemctl("start", item)
            except Exception:
                pass
        raise



def delete_server(sid, confirm=False):
    """Permanently remove a stopped server and its registered backup files."""
    if confirm is not True:
        raise ManagerError("GM-250: Explicit deletion confirmation required")
    item = store.get_server(sid)
    if not item:
        raise ManagerError("GM-108: Server not found")

    name = item["name"]
    if not NAME.fullmatch(name):
        raise ManagerError("GM-251: Refusing to delete a server with an invalid registry name")

    servers_root = settings.SERVERS.resolve()
    raw_root = Path(item["directory"])
    if raw_root.is_symlink():
        raise ManagerError("GM-252: Refusing to delete a symlinked server directory")
    root = raw_root.resolve()
    expected = (servers_root / name).resolve()
    if root != expected or root.parent != servers_root or root == servers_root:
        raise ManagerError("GM-252: Refusing to delete a server directory outside the managed server root")
    if not root.is_dir():
        raise ManagerError("GM-253: Server directory is missing or is not a safe directory")

    backups_root = settings.BACKUPS.resolve()
    backup_paths = []
    for backup in store.list_backups(sid):
        raw_path = Path(backup["filename"])
        if raw_path.is_symlink():
            raise ManagerError("GM-254: Refusing deletion because a registered backup is a symlink")
        path = raw_path.resolve()
        if path.parent != backups_root or not path.is_file():
            raise ManagerError("GM-254: Refusing deletion because a registered backup is missing or outside the managed backup directory")
        backup_paths.append(path)

    if _active(item):
        _systemctl("stop", item)
        if _active(item):
            raise ManagerError("GM-255: Server is still active; deletion aborted")

    quarantine = root.parent / (root.name + ".deleting-" + secrets.token_hex(6))
    root.rename(quarantine)
    cleanup_warnings = []
    try:
        with store.connect() as db:
            cur = db.execute("DELETE FROM servers WHERE id=?", (sid,))
            if cur.rowcount != 1:
                raise ManagerError("GM-108: Server registry entry disappeared during deletion")
        for path in backup_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                cleanup_warnings.append(f"Could not remove backup {path.name}: {exc}")
        log_path = SERVER_LOG_DIR / (name + ".log")
        try:
            log_path.unlink(missing_ok=True)
        except OSError as exc:
            cleanup_warnings.append(f"Could not remove server log: {exc}")
        try:
            shutil.rmtree(quarantine)
        except OSError as exc:
            cleanup_warnings.append(f"Could not remove quarantined server directory {quarantine}: {exc}")
    except Exception:
        if quarantine.exists() and not root.exists():
            quarantine.rename(root)
        raise
    return {"deleted": True, "id": sid, "cleanup_warnings": cleanup_warnings}

def server_status(sid):
    item = store.get_server(sid)
    if not item:
        raise ManagerError("GM-108: Server not found")
    try:
        active = _active(item)
    except ManagerError as exc:
        return {"status": "unknown", "error": str(exc)}
    return {"status": "running" if active else "stopped"}
