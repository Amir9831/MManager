import re,uuid
from pathlib import Path
from . import store
from .ports import choose_port
SERVERS=Path('/var/lib/mmanager/servers'); NAME=re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{1,31}$')
class ManagerError(Exception): pass
def create_server(name,edition,version):
    if not NAME.fullmatch(name): raise ManagerError('GM-101: Invalid name; use 2-32 letters, digits, _ or -')
    if edition not in {'java','bedrock','crossplay'}: raise ManagerError('GM-102: Unsupported edition')
    if not version or len(version)>40: raise ManagerError('GM-103: Invalid version')
    rows=store.list_servers()
    if any(x['name']==name for x in rows): raise ManagerError('GM-104: Server name already exists')
    jp=choose_port(25565,'tcp',{x['java_port'] for x in rows if x['java_port']}) if edition in {'java','crossplay'} else None
    bp=choose_port(19132,'udp',{x['bedrock_port'] for x in rows if x['bedrock_port']}) if edition in {'bedrock','crossplay'} else None
    d=SERVERS/name; d.mkdir(parents=True,exist_ok=False)
    item=dict(id=str(uuid.uuid4()),name=name,edition=edition,version=version,java_port=jp,bedrock_port=bp,directory=str(d))
    try: store.add_server(item)
    except Exception: d.rmdir(); raise
    return item
def delete_server(sid,confirm=False):
    if not confirm: raise ManagerError('GM-105: Explicit confirmation required')
    item=next((x for x in store.list_servers() if x['id']==sid),None)
    if not item: raise ManagerError('GM-106: Server not found')
    store.remove_server(sid)
    return {'removed_from_registry':True,'data_retained':True,'server':item}
