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
    def send_packet(sock, reqid, typ, payload):
        data=struct.pack("<ii",reqid,typ)+payload.encode("utf-8")+b"\0\0"
        sock.sendall(struct.pack("<i",len(data))+data)
    def recv_packet(sock):
        size=struct.unpack("<i",recv_exact(sock,4))[0]
        if size<10 or size>1024*1024: raise ManagerError("Invalid RCON response.")
        body=recv_exact(sock,size)
        rid,rtype=struct.unpack("<ii",body[:8])
        return rid,rtype,body[8:-2].decode("utf-8","replace")
    try:
        with socket.create_connection(("127.0.0.1",port),timeout=3) as s:
            s.settimeout(3)
            send_packet(s,11,3,password)
            auth_id,auth_type,_=recv_packet(s)
            if auth_id==-1: raise ManagerError("RCON authentication failed.")
            if auth_id!=11: raise ManagerError("Unexpected RCON authentication response.")
            send_packet(s,12,2,command)
            send_packet(s,13,0,"")
            responses=[]
            while True:
                rid,_,payload=recv_packet(s)
                if rid==13: break
                if rid==12: responses.append(payload)
            return "".join(responses)
    except OSError as exc: raise ManagerError("RCON unavailable: "+str(exc))

def configure_rcon(sid, enabled, password=None, port=25575):
    item=_server(sid)
    if item["edition"]=="bedrock": raise ManagerError("Bedrock Dedicated Server does not provide Minecraft RCON.")
    if not 1024 <= int(port) <= 65535: raise ManagerError("RCON port must be between 1024 and 65535.")
    if int(port) in {int(item.get("java_port") or 0),int(item.get("bedrock_port") or 0),8765}:
        raise ManagerError("RCON port conflicts with a Minecraft or internal Core port.")
    from .webconfig import load as load_web_config
    if int(port)==int(load_web_config()["port"]): raise ManagerError("RCON port conflicts with the public web panel port.")
    if enabled and (not password or len(password)<16 or len(password)>128):
        raise ManagerError("Set an RCON password of at least 16 characters.")
    from .core import update_server_settings
    changes={"enable-rcon":"true" if enabled else "false","rcon.port":str(int(port))}
    changes["rcon.password"]=password if enabled else ""
    result=update_server_settings(sid,changes)
    return {"enabled":bool(enabled),"port":int(port),"restart_required":True,"saved":True}

def console(sid, command):
    item = _server(sid)
    command = str(command).strip()
    if command.startswith("/"):
        command = command[1:]
    if not command or len(command) > 512 or any(x in command for x in "\r\n\0"):
        raise ManagerError("Command must be 1-512 characters on one line.")
    if item["edition"] == "bedrock":
        was_active = _active(item)
        migrated = ensure_bedrock_console(item)
        if migrated:
            if not was_active:
                raise ManagerError("Bedrock console channel was prepared. Start the server, then send commands.")
            from .core import _systemctl
            _systemctl("restart", item)
            deadline = time.time() + 8
            fifo = Path(item["directory"]) / ".mmanager-console.fifo"
            while time.time() < deadline and not fifo.is_fifo():
                time.sleep(0.2)
        return _bedrock_console(item, command)
    return {"response": _rcon(item, command)}


def players(sid):
    item = _server(sid)
    root = Path(item["directory"])
    online = []
    raw = ""
    if item["edition"] == "bedrock":
        online = _bedrock_online(item)
    else:
        try:
            raw = _rcon(item, "list")
            match = re.search(r"There are \d+ of a max of \d+ players online:?(.*)", raw, re.I | re.S)
            if match:
                online = [{"name": x.strip(), "online": True} for x in match.group(1).split(",") if x.strip()]
        except ManagerError as exc:
            raw = str(exc)
    if item["edition"] == "bedrock":
        allowlist = _read_json(root / "allowlist.json", [])
        permissions = _read_json(root / "permissions.json", [])
        known = {str(x.get("name", "")).lower(): {"name": str(x.get("name", "")), "xuid": str(x.get("xuid", ""))}
                 for x in allowlist if isinstance(x, dict) and x.get("name")}
        for x in online:
            known.setdefault(x["name"].lower(), x)
        admins = []
        for entry in permissions:
            if isinstance(entry, dict) and entry.get("permission") == "operator":
                xuid = str(entry.get("xuid", ""))
                player = next((v for v in known.values() if v.get("xuid") == xuid), {"name": xuid, "xuid": xuid})
                admins.append(player)
        banned = []
        offline = [v for k, v in known.items() if k not in {x["name"].lower() for x in online}]
    else:
        usercache = _read_json(root / "usercache.json", [])
        ops = _read_json(root / "ops.json", [])
        whitelist = _read_json(root / "whitelist.json", [])
        banned = [{"name": str(x.get("name", "")), "uuid": str(x.get("uuid", ""))}
                  for x in _read_json(root / "banned-players.json", []) if isinstance(x, dict)]
        known = {}
        for entry in usercache + ops + whitelist + banned:
            if isinstance(entry, dict) and entry.get("name"):
                known[str(entry["name"]).lower()] = {"name": str(entry["name"]), "uuid": str(entry.get("uuid", ""))}
        admins = [{"name": str(x.get("name", "")), "uuid": str(x.get("uuid", "")), "level": int(x.get("level", 4))}
                  for x in ops if isinstance(x, dict) and x.get("name")]
        online_names = {x["name"].lower() for x in online}
        offline = [v for k, v in known.items() if k not in online_names]
    banned_names = {x["name"].lower() for x in banned}
    for player in online + offline + admins:
        player["banned"] = player["name"].lower() in banned_names
    return {"online": online, "offline": offline, "admins": admins, "banned": banned,
            "raw": raw, "edition": item["edition"], "permission_model": "bedrock" if item["edition"] == "bedrock" else "java"}


def moderate(sid, action, player, reason="", permission_level=4, permission="operator"):
    item = _server(sid)
    player = str(player).strip()
    if not re.fullmatch(r"[A-Za-z0-9_ .-]{1,32}", player) or player in {".", ".."}:
        raise ManagerError("Invalid Minecraft player name.")
    if action not in {"kick", "ban", "pardon", "op", "deop", "permission", "allowlist_add", "allowlist_remove"}:
        raise ManagerError("Unsupported moderation action.")
    reason = re.sub(r"[\r\n\0]", " ", str(reason))[:160]
    if item["edition"] == "bedrock":
        if action in {"ban", "pardon"}:
            raise ManagerError("Bedrock Dedicated Server has no native ban/pardon list. Use Allowlist controls only if allow-list=true; removing a player from an allowlist is not a ban.")
        if action == "op":
            return console(sid, 'op "' + player + '"')
        if action == "deop":
            return console(sid, 'deop "' + player + '"')
        if action == "kick":
            return console(sid, 'kick "' + player + '"' + (" " + reason if reason else ""))
        if action == "allowlist_add":
            if core.server_settings(sid)["settings"].get("allow-list", "false").lower() != "true":
                raise ManagerError("Enable allow-list=true first; otherwise allowlist removal cannot block access.")
            return console(sid, 'allowlist add "' + player + '"')
        if action == "allowlist_remove":
            if core.server_settings(sid)["settings"].get("allow-list", "false").lower() != "true":
                raise ManagerError("Enable allow-list=true first; otherwise allowlist removal cannot block access.")
            return console(sid, 'allowlist remove "' + player + '"')
        if permission not in {"operator", "member", "visitor"}:
            raise ManagerError("Bedrock permission must be operator, member or visitor.")
        allowlist = _read_json(Path(item["directory"]) / "allowlist.json", [])
        online = _bedrock_online(item)
        match = next((x for x in allowlist if isinstance(x, dict) and str(x.get("name", "")).lower() == player.lower()), None)
        if not match:
            match = next((x for x in online if x["name"].lower() == player.lower()), None)
        xuid = str((match or {}).get("xuid", ""))
        if not xuid:
            raise ManagerError("Bedrock XUID not found. The player must join once or be added to allowlist first.")
        path = Path(item["directory"]) / "permissions.json"
        entries = _read_json(path, [])
        entries = [x for x in entries if not (isinstance(x, dict) and str(x.get("xuid", "")) == xuid)]
        if permission != "member":
            entries.append({"permission": permission, "xuid": xuid})
        path.write_text(json.dumps(entries, indent=2) + "\n")
        return console(sid, "permission reload")
    if action == "op":
        if not 1 <= int(permission_level) <= 4:
            raise ManagerError("Java operator level must be between 1 and 4.")
        response = _rcon(item, "op " + player)
        path = Path(item["directory"]) / "ops.json"
        entries = _read_json(path, [])
        for entry in entries:
            if isinstance(entry, dict) and str(entry.get("name", "")).lower() == player.lower():
                entry["level"] = int(permission_level)
        path.write_text(json.dumps(entries, indent=2) + "\n")
        return {"action": action, "player": player, "response": response, "permission_level": int(permission_level)}
    if action == "deop":
        command = "deop " + player
    elif action == "kick":
        command = "kick " + player + (" " + reason if reason else "")
    elif action == "ban":
        command = "ban " + player + (" " + reason if reason else "")
    else:
        command = "pardon " + player
    return {"action": action, "player": player, "response": _rcon(item, command)}


def _bedrock_console(item, command):
    fifo = Path(item["directory"]) / ".mmanager-console.fifo"
    if not fifo.is_fifo():
        raise ManagerError("Bedrock console channel is not initialized. Restart the server once after updating MManager.")
    try:
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, (command + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except OSError as exc:
        raise ManagerError("Cannot send command to Bedrock console: " + str(exc))
    return {"response": "Command sent to Bedrock console. See the Logs tab for command output."}


def ensure_bedrock_console(item):
    root = Path(item["directory"])
    script = root / "run.sh"
    current = script.read_text(errors="replace") if script.exists() else ""
    if ".mmanager-console.fifo" in current:
        return False
    fifo = root / ".mmanager-console.fifo"
    if fifo.exists() and not fifo.is_fifo():
        raise ManagerError("Refusing to replace a non-FIFO Bedrock console path.")
    wrapper = ("#!/bin/sh\ncd " + str(root) + "\n"
               'FIFO=".mmanager-console.fifo"\n'
               '[ -p "$FIFO" ] || mkfifo "$FIFO"\n'
               'exec 3<> "$FIFO"\n'
               'LD_LIBRARY_PATH=. exec ./bedrock_server <&3\n')
    script.write_text(wrapper)
    script.chmod(0o750)
    return True


def _read_json(path, default):
    try:
        data = json.loads(Path(path).read_text())
        return data if isinstance(data, list) else default
    except (OSError, ValueError, TypeError):
        return default


def _bedrock_online(item):
    try:
        logs = subprocess.run(
            ["/usr/bin/journalctl", "--quiet", "-u", "mmanager-mc@" + item["name"] + ".service",
             "--no-pager", "-o", "cat", "-n", "2000"],
            capture_output=True, text=True, timeout=10, check=True).stdout
    except Exception:
        logs = ""
    states = {}
    for line in logs.splitlines():
        connected = re.search(r"Player connected:\s*(.*?),\s*xuid:\s*([0-9]+)", line, re.I)
        disconnected = re.search(r"Player disconnected:\s*(.*?),\s*xuid:\s*([0-9]+)", line, re.I)
        match = connected or disconnected
        if match:
            name, xuid = match.group(1).strip(), match.group(2)
            states[name.lower()] = {"name": name, "xuid": xuid, "online": bool(connected)}
    return [x for x in states.values() if x["online"]]

def _proc_cpu_ticks(raw):
    """Read utime+stime from /proc/<pid>/stat without being confused by spaces in comm."""
    close = raw.rfind(")")
    if close < 0:
        raise ValueError("Malformed /proc stat")
    fields = raw[close + 2:].split()  # starts at field 3 (state)
    if len(fields) <= 12:
        raise ValueError("Incomplete /proc stat")
    return int(fields[11]) + int(fields[12])


def _find_server_pid(item):
    """Find the Minecraft process owned by mmanager without privileged systemctl/sudo."""
    expected = Path(item["directory"]).resolve()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        proc = Path("/proc") / entry.name
        try:
            if proc.stat().st_uid != os.geteuid():
                continue
            cwd = Path(os.readlink(proc / "cwd")).resolve()
            if cwd != expected:
                continue
            cmdline = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
            if "bedrock_server" in cmdline or ("server.jar" in cmdline and "java" in cmdline):
                return int(entry.name)
        except (OSError, PermissionError, ProcessLookupError):
            continue
    return 0


def telemetry(sid):
    item = _server(sid)
    pid = _find_server_pid(item)
    if pid <= 0:
        return {"status": "stopped", "cpu_percent": 0.0, "memory_bytes": 0, "memory_percent": 0.0, "pid": None}
    proc = Path("/proc") / str(pid)
    try:
        stat1 = _proc_cpu_ticks((proc / "stat").read_text())
        total1 = sum(int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:])
        time.sleep(0.30)
        stat2 = _proc_cpu_ticks((proc / "stat").read_text())
        total2 = sum(int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:])
        status = (proc / "status").read_text()
        rss_match = re.search(r"VmRSS:\s+(\d+)\s+kB", status)
        if not rss_match:
            raise ValueError("VmRSS is unavailable")
        memory = int(rss_match.group(1)) * 1024
        mem_total_match = re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text())
        if not mem_total_match:
            raise ValueError("MemTotal is unavailable")
        mem_total = int(mem_total_match.group(1)) * 1024
        cpu_count = os.cpu_count() or 1
        cpu = 100.0 * cpu_count * max(0, stat2 - stat1) / max(1, total2 - total1)
        return {"status": "running", "pid": pid,
                "cpu_percent": round(min(cpu, 100.0 * cpu_count), 1),
                "memory_bytes": memory,
                "memory_percent": round(100.0 * memory / max(1, mem_total), 2)}
    except FileNotFoundError:
        return {"status": "stopped", "cpu_percent": 0.0, "memory_bytes": 0, "memory_percent": 0.0, "pid": None}
    except (OSError, AttributeError, ValueError, IndexError) as exc:
        raise ManagerError("Cannot read process telemetry: " + str(exc))


def _bedrock_console(item, command):
    fifo = Path(item["directory"]) / ".mmanager-console.fifo"
    if not fifo.is_fifo():
        raise ManagerError("Bedrock console channel is not initialized. Restart the server once after updating MManager.")
    try:
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, (command + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except OSError as exc:
        raise ManagerError("Cannot send command to Bedrock console: " + str(exc))
    return {"response": "Command sent to Bedrock console. See the Logs tab for command output."}


def ensure_bedrock_console(item):
    """Migrate existing BDS run.sh to an stdin FIFO so the panel can send commands."""
    root = Path(item["directory"])
    script = root / "run.sh"
    current = script.read_text(errors="replace") if script.exists() else ""
    if ".mmanager-console.fifo" in current:
        return False
    fifo = root / ".mmanager-console.fifo"
    if fifo.exists() and not fifo.is_fifo():
        raise ManagerError("Refusing to replace a non-FIFO Bedrock console path.")
    wrapper = ("#!/bin/sh\ncd " + str(root) + "\n"
               'FIFO=".mmanager-console.fifo"\n'
               '[ -p "$FIFO" ] || mkfifo "$FIFO"\n'
               'exec 3<> "$FIFO"\n'
               'LD_LIBRARY_PATH=. exec ./bedrock_server <&3\n')
    script.write_text(wrapper)
    script.chmod(0o750)
    return True


def _read_json(path, default):
    try:
        data = json.loads(Path(path).read_text())
        return data if isinstance(data, list) else default
    except (OSError, ValueError, TypeError):
        return default


def _bedrock_online(item):
    try:
        logs = subprocess.run(
            ["/usr/bin/journalctl", "--quiet", "-u", "mmanager-mc@" + item["name"] + ".service",
             "--no-pager", "-o", "cat", "-n", "2000"],
            capture_output=True, text=True, timeout=10, check=True).stdout
    except Exception:
        logs = ""
    states = {}
    for line in logs.splitlines():
        connected = re.search(r"Player connected:\s*(.*?),\s*xuid:\s*([0-9]+)", line, re.I)
        disconnected = re.search(r"Player disconnected:\s*(.*?),\s*xuid:\s*([0-9]+)", line, re.I)
        match = connected or disconnected
        if match:
            name, xuid = match.group(1).strip(), match.group(2)
            states[name.lower()] = {"name": name, "xuid": xuid, "online": bool(connected)}
    return [x for x in states.values() if x["online"]]


def players(sid):
    item = _server(sid)
    root = Path(item["directory"])
    online = []
    raw = ""
    if item["edition"] == "bedrock":
        online = _bedrock_online(item)
    else:
        try:
            raw = _rcon(item, "list")
            match = re.search(r"There are \d+ of a max of \d+ players online:?(.*)", raw, re.I | re.S)
            if match:
                online = [{"name": x.strip(), "online": True} for x in match.group(1).split(",") if x.strip()]
        except ManagerError as exc:
            raw = str(exc)
    if item["edition"] == "bedrock":
        allowlist = _read_json(root / "allowlist.json", [])
        permissions = _read_json(root / "permissions.json", [])
        known = {str(x.get("name", "")).lower(): {"name": str(x.get("name", "")), "xuid": str(x.get("xuid", ""))}
                 for x in allowlist if isinstance(x, dict) and x.get("name")}
        for x in online:
            known.setdefault(x["name"].lower(), x)
        admins = []
        for entry in permissions:
            if isinstance(entry, dict) and entry.get("permission") == "operator":
                xuid = str(entry.get("xuid", ""))
                player = next((v for v in known.values() if v.get("xuid") == xuid), {"name": xuid, "xuid": xuid})
                admins.append(player)
        banned = []
        offline = [v for k, v in known.items() if k not in {x["name"].lower() for x in online}]
    else:
        usercache = _read_json(root / "usercache.json", [])
        ops = _read_json(root / "ops.json", [])
        whitelist = _read_json(root / "whitelist.json", [])
        banned = [{"name": str(x.get("name", "")), "uuid": str(x.get("uuid", ""))}
                  for x in _read_json(root / "banned-players.json", []) if isinstance(x, dict)]
        known = {}
        for entry in usercache + ops + whitelist + banned:
            if isinstance(entry, dict) and entry.get("name"):
                known[str(entry["name"]).lower()] = {"name": str(entry["name"]), "uuid": str(entry.get("uuid", ""))}
        admins = [{"name": str(x.get("name", "")), "uuid": str(x.get("uuid", "")), "level": int(x.get("level", 4))}
                  for x in ops if isinstance(x, dict) and x.get("name")]
        online_names = {x["name"].lower() for x in online}
        offline = [v for k, v in known.items() if k not in online_names]
    banned_names = {x["name"].lower() for x in banned}
    for player in online + offline + admins:
        player["banned"] = player["name"].lower() in banned_names
    return {"online": online, "offline": offline, "admins": admins, "banned": banned,
            "raw": raw, "edition": item["edition"], "permission_model": "bedrock" if item["edition"] == "bedrock" else "java"}


def moderate(sid, action, player, reason="", permission_level=4):
    item = _server(sid)
    player = str(player).strip()
    if not re.fullmatch(r"[A-Za-z0-9_ .-]{1,32}", player) or player in {".", ".."}:
        raise ManagerError("Invalid Minecraft player name.")
    if action not in {"kick", "ban", "pardon", "op", "deop"}:
        raise ManagerError("Unsupported moderation action.")
    reason = re.sub(r"[\r\n\0]", " ", str(reason))[:160]
    if item["edition"] == "bedrock":
        if action == "op":
            cmd = 'op "' + player + '"'
        elif action == "deop":
            cmd = 'deop "' + player + '"'
        elif action == "kick":
            cmd = 'kick "' + player + '"' + (" " + reason if reason else "")
        elif action in {"ban", "pardon"}:
            raise ManagerError("Bedrock Dedicated Server has no native player ban list. Use allowlist management to restrict access; this is not the same as a ban.")
        return _bedrock_console(item, cmd)
    if action == "op":
        if not 1 <= int(permission_level) <= 4:
            raise ManagerError("Java operator level must be between 1 and 4.")
        command = "op " + player + " " + str(int(permission_level))
    elif action == "deop":
        command = "deop " + player
    elif action == "kick":
        command = "kick " + player + (" " + reason if reason else "")
    elif action == "ban":
        command = "ban " + player + (" " + reason if reason else "")
    else:
        command = "pardon " + player
    return {"action": action, "player": player, "response": _rcon(item, command)}

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
    if item["version"] not in v.get("game_versions",[]):
        raise ManagerError("Selected plugin release does not support this Minecraft version.")
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
