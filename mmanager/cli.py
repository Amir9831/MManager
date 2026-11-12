import os,shutil,subprocess,sys
from getpass import getpass
from argon2 import PasswordHasher
from . import store,core,auth
from .settings import AUTH_FILE,TOKEN_FILE,CONFIG
from .webconfig import ensure,save

def ctl(a,u):
 cmd=["systemctl",a,u]
 if os.geteuid()!=0: cmd=["sudo","-n",*cmd]
 return subprocess.run(cmd,check=False).returncode == 0

def web_menu():
 while True:
  cfg=ensure()
  print("\nWeb panel management")
  print(f"1 Change panel path (current: /{cfg['path']}/)")
  print(f"2 Change administrator password")
  print(f"3 Change panel port (current: {cfg['port']})")
  print("4 Show panel URL")
  print("0 Back")
  c=input("> ").strip()
  if c=="0": return
  if c=="1":
   value=input("New path (blank = generate random): ").strip().strip("/")
   if not value:
    import secrets
    value=secrets.token_urlsafe(24)
   if len(value)<24 or not value.replace("-","").replace("_","").isalnum():
    print("Path must be at least 24 URL-safe characters."); continue
   cfg["path"]=value
   save(cfg)
   if ctl("restart","mmanager-web.service"): print("Path updated.")
   else: print("Saved, but web service restart failed; run: sudo systemctl restart mmanager-web")
  elif c=="2":
   p=getpass("New administrator password (min 12 chars): ")
   if len(p)<12: print("Password must be at least 12 characters."); continue
   if p!=getpass("Confirm password: "): print("Passwords do not match."); continue
   import json
   data=json.loads(AUTH_FILE.read_text())
   data["password_hash"]=PasswordHasher().hash(p)
   tmp=AUTH_FILE.with_suffix(".tmp"); tmp.write_text(json.dumps(data)); tmp.chmod(0o640); tmp.replace(AUTH_FILE)
   TOKEN_FILE.write_text(__import__("secrets").token_urlsafe(48)); TOKEN_FILE.chmod(0o640)
   print("Administrator password changed; all existing browser sessions have been invalidated.")
  elif c=="3":
   raw=input("New TCP port (1024-65535): ").strip()
   try: port=int(raw)
   except ValueError: print("Invalid port."); continue
   if not 1024<=port<=65535: print("Port must be between 1024 and 65535."); continue
   cfg["port"]=port; save(cfg)
   env=CONFIG / "web.env"; env.write_text(f"UVICORN_PORT={port}\n"); env.chmod(0o640)
   if ctl("restart","mmanager-web.service"): print("Port updated.")
   else: print("Saved, but web service restart failed; check whether the port is already in use.")
  elif c=="4":
   import urllib.request
   try: ip=urllib.request.urlopen("https://api.ipify.org",timeout=5).read().decode().strip()
   except Exception: ip="<PUBLIC_IP>"
   print(f"Panel: http://{ip}:{cfg['port']}/{cfg['path']}/")
  else: print("Invalid selection")


def update_manager():
 print("\nChecking for MManager updates...")
 if os.geteuid()!=0:
  print("Run the CLI with sudo to update MManager."); return
 import urllib.request
 url="https://raw.githubusercontent.com/Amir9831/MManager/main/install.sh"
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"MManager-Updater"})
  with urllib.request.urlopen(req,timeout=30) as response: script=response.read()
  if not script.startswith(b"#!/usr/bin/env bash"): raise RuntimeError("Unexpected installer content")
  print("Starting official installer. Existing worlds and backups are preserved.")
  subprocess.run(["/usr/bin/bash","-s"],input=script,check=True)
 except Exception as exc: print("[UPDATE FAILED]",exc)

def main():
 while True:
  print("\nMManager\n1 Server management\n2 Restart Core\n3 Restart Web\n4 Start services\n5 Stop services\n6 Diagnostics\n7 Web panel management\n8 Update MManager\n0 Exit")
  c=input("> ").strip()
  if c=="0": return
  if c=="1":
   rows=store.list_servers()
   for s in rows: print(s["name"],s["software"],s["version"],"port",s["java_port"])
   if rows:
    name=input("Server name (blank to return): ").strip()
    item=next((x for x in rows if x["name"]==name),None)
    if item:
     a=input("Action start/stop/restart/logs: ").strip()
     try:
      if a=="logs": print(core.server_logs(item["id"]))
      elif a in {"start","stop","restart"}: core.server_action(item["id"],a)
      else: print("Invalid action")
     except Exception as e: print("[ERROR]",e)
  elif c=="2": ctl("restart","mmanager-core.service")
  elif c=="3": ctl("restart","mmanager-web.service")
  elif c=="4":
   ctl("start","mmanager-core.service"); ctl("start","mmanager-web.service")
  elif c=="5":
   ctl("stop","mmanager-web.service"); ctl("stop","mmanager-core.service")
  elif c=="6": subprocess.run(["systemctl","--failed","--no-pager"])
  elif c=="7": web_menu()\n  elif c=="8": update_manager()
  else: print("Invalid selection")
