import os,shutil,subprocess
from . import store,core
def ctl(a,u):
 cmd=["systemctl",a,u]
 if os.geteuid()!=0: cmd=["sudo","-n",*cmd]
 subprocess.run(cmd,check=False)
def main():
 while True:
  print("\nMManager\n1 Servers\n2 Restart Core\n3 Restart Web\n4 Start services\n5 Stop services\n6 Diagnostics\n0 Exit")
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
  else: print("Invalid selection")
