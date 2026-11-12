"""Authenticated management helpers: RCON, telemetry and Modrinth plugins."""
import json, os, re, socket, struct, subprocess, time, urllib.parse, urllib.request
from pathlib import Path
from . import store
from .core import ManagerError, _active

def _server(sid):
    item=store.get_server(sid)
    if not item: raise ManagerError("GM-108: Server not found")
    return item

def _rcon(item, command):
    if item["edition"] == "bedrock":
        raise ManagerError("RCON is not supported by Bedrock Dedicated Server.")
    settings={}
    path=Path(item["directory"])/"server.properties"
    for line in path.read_text(errors="replace").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k,v=line.split("=",1); settings[k.strip()]=v.strip()
    if settings.get("enable-rcon","false").lower() != "true":
        raise ManagerError("RCON is disabled. Enable it in the RCON settings first.")
    password=settings.get("rcon.password","")
    if not password: raise ManagerError("RCON password is not configured.")
    try: port=int(settings.get("rcon.port","25575"))
    except ValueError: raise ManagerError("Invalid RCON port.")
    def recv_exact(sock, size):
        chunks=b""
        while len(chunks)<size:
            part=sock.recv(size-len(chunks))
            if not part: raise ManagerError("RCON connection closed.")
            chunks+=part
        return chunks
    def packet(sock, reqid, typ, payload):
        data=struct.pack("<ii",reqid,typ)+payload.encode("utf-8")+b"\0\0"
        sock.sendall(struct.pack("<i",len(data))+data)
        head=recv_exact(sock,4)
        size=struct.unpack("<i",head)[0]
        if size<10 or size>1024*1024: raise ManagerError("Invalid RCON response.")
        body=b""
        body=recv_exact(sock,size)
        rid,rtype=struct.unpack("<ii",body[:8])
        if rid == -1: raise ManagerError("RCON authentication failed.")
        return body[8:-2].decode("utf-8","replace")
    try:
        with socket.create_connection(("127.0.0.1",port),timeout=3) as s:
            s.settimeout(3)
            packet(s,11,3,password)
            return packet(s,12,2,command)
    except OSError as exc: raise ManagerError("RCON unavailable: "+str(exc))

def configure_rcon(sid, enabled, password=None, port=25575):
    item=_server(sid)
    if item["edition"]=="bedrock": raise ManagerError("Bedrock Dedicated Server does not provide Minecraft RCON.")
    if not 1024 <= int(port) <= 65535: raise ManagerError("RCON port must be between 1024 and 65535.")
    if enabled and (not password or len(password)<16 or len(password)>128):
        raise ManagerError("Set an RCON password of at least 16 characters.")
    from .core import update_server_settings
    changes={"enable-rcon":"true" if enabled else "false","rcon.port":str(int(port)),"rcon.ip":"127.0.0.1"}
    changes["rcon.password"]=password if enabled else ""
    result=update_server_settings(sid,changes)
    return {"enabled":bool(enabled),"port":int(port),"restart_required":True,"saved":True}

def console(sid, command):
    _server(sid)
    command=str(command).strip()
    if not command or len(command)>512 or any(c in command for c in "\r\n\0"):
        raise ManagerError("Command must be 1-512 characters on one line.")
    return {"response":_rcon(_server(sid),command)}

def players(sid):
    item=_server(sid)
    raw=_rcon(item,"list")
    names=[]
    match=re.search(r"There are \d+ of a max of \d+ players online:?(.*)",raw,re.I|re.S)
    if match:
        names=[x.strip() for x in match.group(1).split(",") if x.strip()]
    return {"online":names,"count":len(names),"raw":raw}

def moderate(sid, action, player, reason=""):
    _server(sid)
    if action not in {"kick","ban","pardon"}: raise ManagerError("Unsupported moderation action.")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,16}",player): raise ManagerError("Invalid Minecraft player name.")
    reason=re.sub(r"[\r\n\0]"," ",str(reason))[:160]
    cmd={"kick":"kick "+player+(" "+reason if reason else ""),
         "ban":"ban "+player+(" "+reason if reason else ""),
         "pardon":"pardon "+player}[action]
    return {"action":action,"player":player,"response":_rcon(_server(sid),cmd)}

def telemetry(sid):
    item=_server(sid)
    unit="mmanager-mc@"+item["name"]+".service"
    p=subprocess.run(["/usr/bin/systemctl","show",unit,"--property=MainPID","--value"],capture_output=True,text=True,timeout=5)
    if p.returncode: raise ManagerError("Cannot read server process information.")
    try: pid=int(p.stdout.strip())
    except ValueError: pid=0
    if pid<=0: return {"status":"stopped","cpu_percent":0,"memory_bytes":0,"memory_percent":0}
    proc=Path("/proc")/str(pid)
    try:
        status=(proc/"status").read_text()
        rss_kb=int(re.search(r"VmRSS:\s+(\d+)\s+kB",status).group(1))
        stat1=(proc/"stat").read_text().split()
        total1=sum(int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:])
        ticks1=int(stat1[13])+int(stat1[14])
        time.sleep(.35)
        stat2=(proc/"stat").read_text().split()
        total2=sum(int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:])
        ticks2=int(stat2[13])+int(stat2[14])
        cpu=max(0.0,100.0*(os.cpu_count() or 1)*(ticks2-ticks1)/max(1,total2-total1))
        mem_total=int(re.search(r"MemTotal:\s+(\d+)",Path("/proc/meminfo").read_text()).group(1))*1024
        mem=rss_kb*1024
        return {"status":"running","pid":pid,"cpu_percent":round(cpu,1),"memory_bytes":mem,"memory_percent":round(100*mem/max(1,mem_total),2)}
    except (OSError,AttributeError,ValueError,IndexError) as exc:
        raise ManagerError("Cannot read process telemetry: "+str(exc))

def plugin_search(query):
    query=str(query).strip()[:100]
    if not query: raise ManagerError("Enter a plugin name to search.")
    url="https://api.modrinth.com/v2/search?"+urllib.parse.urlencode({"query":query,"facets":'[["project_type:plugin"]]',"limit":"10"})
    req=urllib.request.Request(url,headers={"User-Agent":"MManager/0.4 (https://github.com/Amir9831/MManager)"})
    with urllib.request.urlopen(req,timeout=20) as r: data=json.load(r)
    return {"results":[{"project_id":x["project_id"],"slug":x["slug"],"title":x["title"],"description":x.get("description","")[:240],"downloads":x.get("downloads",0)} for x in data.get("hits",[])]}


def plugin_versions(project_id, game_version):
    if not re.fullmatch(r"[A-Za-z0-9_-]{5,64}",str(project_id)): raise ManagerError("Invalid Modrinth project ID.")
    req=urllib.request.Request("https://api.modrinth.com/v2/project/"+project_id+"/version",headers={"User-Agent":"MManager/0.4"})
    with urllib.request.urlopen(req,timeout=20) as r: versions=json.load(r)
    result=[]
    for v in versions:
        loaders=v.get("loaders",[])
        if not ({"paper","spigot","purpur"} & set(loaders)): continue
        games=v.get("game_versions",[])
        if game_version not in games: continue
        file=next((x for x in v.get("files",[]) if x.get("primary") and x.get("filename","").endswith(".jar")),None)
        if file: result.append({"version_id":v["id"],"version":v.get("version_number",""),"name":file["filename"],"date":v.get("date_published","")})
        if len(result)>=10: break
    return {"versions":result}

def installed_plugins(sid):
    item=_server(sid)
    if item["software"]!="paper": raise ManagerError("Plugin management requires Paper (also used by Cross-play).")
    folder=Path(item["directory"])/"plugins"
    return {"items":[{"name":p.name,"size":p.stat().st_size} for p in sorted(folder.glob("*.jar")) if p.is_file()]}

def install_plugin(sid, version_id):
    item=_server(sid)
    if item["software"]!="paper": raise ManagerError("Plugin management requires Paper.")
    if _active(item): raise ManagerError("Stop the server before installing a plugin.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}",str(version_id)): raise ManagerError("Invalid Modrinth version ID.")
    req=urllib.request.Request("https://api.modrinth.com/v2/version/"+version_id,headers={"User-Agent":"MManager/0.4"})
    with urllib.request.urlopen(req,timeout=20) as r: v=json.load(r)
    if "paper" not in v.get("loaders",[]) and "spigot" not in v.get("loaders",[]) and "purpur" not in v.get("loaders",[]):
        raise ManagerError("Selected release is not marked for Paper/Spigot/Purpur.")
    file=next((f for f in v.get("files",[]) if f.get("primary")),None)
    if not file or not file["filename"].endswith(".jar"): raise ManagerError("Modrinth release has no primary JAR file.")
    dest=Path(item["directory"])/"plugins"/Path(file["filename"]).name
    if dest.exists(): raise ManagerError("A plugin with that filename already exists.")
    parsed=urllib.parse.urlparse(file["url"])
    if parsed.scheme!="https" or parsed.hostname not in {"cdn.modrinth.com","cdn-raw.modrinth.com"}:
        raise ManagerError("Untrusted plugin download host.")
    import hashlib
    digest=hashlib.sha512()
    try:
        with urllib.request.urlopen(urllib.request.Request(file["url"],headers={"User-Agent":"MManager/0.4"}),timeout=60) as r, dest.open("xb") as out:
            total=0
            while True:
                chunk=r.read(1024*1024)
                if not chunk: break
                total+=len(chunk)
                if total>100*1024*1024: raise ManagerError("Plugin download exceeds 100 MiB.")
                digest.update(chunk);out.write(chunk)
        expected=file.get("hashes",{}).get("sha512")
        if expected and digest.hexdigest().lower()!=expected.lower():
            raise ManagerError("Plugin checksum mismatch; installation aborted.")
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return {"installed":dest.name,"version":v.get("version_number")}

def remove_plugin(sid, filename):
    item=_server(sid)
    if item["software"]!="paper": raise ManagerError("Plugin management requires Paper.")
    if _active(item): raise ManagerError("Stop the server before removing a plugin.")
    name=Path(str(filename)).name
    if name!=filename or not name.endswith(".jar"): raise ManagerError("Invalid plugin filename.")
    if item["edition"]=="crossplay" and name.lower() in {"geyser-spigot.jar","floodgate-spigot.jar"}:
        raise ManagerError("Core Cross-play plugins cannot be removed from the plugin manager.")
    target=Path(item["directory"])/"plugins"/name
    if not target.is_file() or target.is_symlink(): raise ManagerError("Plugin file not found.")
    target.unlink()
    return {"removed":name}
