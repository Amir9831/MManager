import os,shutil,subprocess,sys
from . import store
CORE='mmanager-core.service'; WEB='mmanager-web.service'
def ctl(action,unit):
 if os.geteuid()!=0: print('[ERROR] Run as root: sudo Mmanager'); return
 if not shutil.which('systemctl'): print('[ERROR] systemctl unavailable'); return
 subprocess.run(['systemctl',action,unit],check=False)
def menu(title,items):
 while True:
  print('\n'+title)
  for i,(label,fn) in enumerate(items,1): print(f'{i}. {label}')
  print('0. Back'); c=input('> ').strip()
  if c=='0': return
  if c.isdigit() and 1<=int(c)<=len(items): items[int(c)-1][1]()
  else: print('[GM-001] Invalid selection')
def servers():
 def listing():
  rows=store.list_servers()
  if not rows: print('No servers registered')
  for s in rows: print(f"{s['name']} | {s['edition']} | {s['version']} | TCP:{s['java_port']} UDP:{s['bedrock_port']}")
 menu('Minecraft Servers',[('List servers',listing),('Create server (runtime adapter pending)',lambda:print('Creation UI is not enabled until runtime download validation is complete.')),('Delete server (safe deletion pending)',lambda:print('Deletion disabled until backup and confirmation workflow is ready.'))])
def main():
 while True:
  os.system('clear' if sys.stdout.isatty() else 'true')
  print('''╔══════════════════════════════════════════════╗
║               MManager Control               ║
╠══════════════════════════════════════════════╣
║  1. Minecraft Servers                         ║
║  2. Web Panel                                 ║
║  3. Core Engine                               ║
║  4. Port Management                           ║
║  5. Backup & Restore                           ║
║  6. Diagnostics & Auto Repair                  ║
║  7. View Logs                                 ║
║  8. Settings                                  ║
║  9. Update MManager                            ║
║ 10. Restart Core                              ║
║ 11. Restart Web Panel                         ║
║ 12. Start / Stop Services                     ║
║  0. Exit                                      ║
╚══════════════════════════════════════════════╝''')
  c=input('Select option: ').strip()
  if c=='0': return
  if c=='1': servers()
  elif c=='2': menu('Web Panel',[('Start',lambda:ctl('start',WEB)),('Stop',lambda:ctl('stop',WEB)),('Restart',lambda:ctl('restart',WEB)),('Status',lambda:subprocess.run(['systemctl','--no-pager','status',WEB]))])
  elif c=='3': menu('Core Engine',[('Start',lambda:ctl('start',CORE)),('Stop',lambda:ctl('stop',CORE)),('Restart',lambda:ctl('restart',CORE)),('Status',lambda:subprocess.run(['systemctl','--no-pager','status',CORE]))])
  elif c=='9': print('GM-901: updater disabled until signed release verification and rollback are implemented')
  elif c=='10': ctl('restart',CORE)
  elif c=='11': ctl('restart',WEB)
  elif c=='12': menu('Services',[('Start both',lambda:(ctl('start',CORE),ctl('start',WEB))),('Stop both',lambda:(ctl('stop',WEB),ctl('stop',CORE))),('Restart both',lambda:(ctl('restart',CORE),ctl('restart',WEB)))])
  elif c=='7':
   p='/var/log/mmanager'
   if os.path.isdir(p):
    for f in os.listdir(p):
     if f.endswith('.log'): subprocess.run(['tail','-n','60',os.path.join(p,f)])
   else: print('No logs found')
  else: print('This module is planned; no system changes were made.')
  input('Press Enter to continue...')
