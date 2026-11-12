from fastapi import FastAPI,HTTPException,Depends,Header,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from .webconfig import load as load_web_config
from pydantic import BaseModel,Field
from . import store,core,auth,advanced
app=FastAPI(title="MManager API",version="0.3.0")
app.add_middleware(CORSMiddleware,allow_origins=[],allow_credentials=False,allow_methods=["GET","POST","PUT","DELETE"],allow_headers=["Content-Type","Authorization"])
class Login(BaseModel): password:str=Field(min_length=1,max_length=256)
class SetupServer(BaseModel):
 edition:str=Field(pattern="^(java|bedrock|crossplay)$")
 software:str=Field(pattern="^(vanilla|paper|bedrock)$")
 version:str=Field(min_length=1,max_length=40)
 accept_eula:bool=False
class SettingsUpdate(BaseModel): settings:dict[str,str]
class RCONConfig(BaseModel):
 enabled:bool
 password:str|None=None
 port:int=25575
class ConsoleCommand(BaseModel): command:str
class Moderation(BaseModel):
 action:str
 player:str
 reason:str=""
class PluginInstall(BaseModel): version_id:str
class ServerUpdate(BaseModel): version:str
def secured(authorization:str|None=Header(default=None)):
 token=authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
 if not auth.verify_token(token): raise HTTPException(401,detail="Authentication required")
 return True
def current_server():
 rows=store.list_servers()
 return rows[0] if rows else None
@app.get("/api/health")
def health(): return {"status":"ok","version":"0.3.0"}
@app.post("/api/login")
def login(p:Login,request:Request):
 token=auth.verify_login(p.password,request.client.host if request.client else "unknown")
 if not token: raise HTTPException(401,detail="Invalid credentials or rate limit reached")
 return {"token":token}
@app.get("/api/server")
def server(_:bool=Depends(secured)): return {"server":current_server()}
@app.get("/api/server/status")
def status(_:bool=Depends(secured)):
 item=current_server()
 if not item:return {"status":"not_configured"}
 try:return core.server_status(item["id"])
 except core.ManagerError as e:raise HTTPException(400,detail=str(e))
@app.get("/api/versions")
def versions(edition:str="java",_:bool=Depends(secured)):
 try:return core.available_versions(edition)
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))
@app.post("/api/server/setup")
def setup(p:SetupServer,_:bool=Depends(secured)):
 if current_server():raise HTTPException(409,detail="A server is already configured. MManager manages one server.")
 if p.edition=="bedrock" and p.software!="bedrock":raise HTTPException(400,detail="Bedrock edition requires Bedrock Dedicated Server software")
 if p.edition=="crossplay" and p.software!="paper":raise HTTPException(400,detail="Cross-play requires Paper + Geyser/Floodgate")
 if p.edition=="java" and p.software not in {"vanilla","paper"}:raise HTTPException(400,detail="Choose Vanilla or Paper for Java Edition")
 try:return core.create_server("minecraft",p.edition,p.version,p.software,p.accept_eula)
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))
@app.post("/api/server/actions/{action}")
def action(action:str,_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return core.server_action(item["id"],action)
 except core.ManagerError as e:raise HTTPException(400,detail=str(e))
@app.get("/api/server/logs")
def logs(lines:int=200,_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return {"logs":core.server_logs(item["id"],lines)}
 except core.ManagerError as e:raise HTTPException(400,detail=str(e))
@app.get("/api/server/settings")
def get_settings(_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:
  result=core.server_settings(item["id"]); result["settings"].pop("rcon.password",None); return result
 except core.ManagerError as e:raise HTTPException(400,detail=str(e))
@app.put("/api/server/settings")
def put_settings(p:SettingsUpdate,_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return core.update_server_settings(item["id"],p.settings)
 except core.ManagerError as e:raise HTTPException(400,detail=str(e))
@app.post("/api/server/backups")
def backup(_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return core.create_backup(item["id"])
 except (core.ManagerError,OSError) as e:raise HTTPException(400,detail=str(e))
@app.get("/api/server/backups")
def backups(_:bool=Depends(secured)):
 item=current_server()
 if not item: return {"items":[]}
 try:return {"items":core.list_backups(item["id"])}
 except core.ManagerError as e:raise HTTPException(400,detail=str(e))
@app.post("/api/server/backups/{bid}/restore")
def restore(bid:str,confirm:bool=False,_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return core.restore_backup(item["id"],bid,confirm)
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))

@app.get("/api/server/telemetry")
def telemetry(_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return advanced.telemetry(item["id"])
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))
@app.post("/api/server/rcon")
def rcon_config(p:RCONConfig,_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return advanced.configure_rcon(item["id"],p.enabled,p.password,p.port)
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))
@app.post("/api/server/console")
def console(p:ConsoleCommand,_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return advanced.console(item["id"],p.command)
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))
@app.get("/api/server/players")
def players(_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return advanced.players(item["id"])
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))
@app.post("/api/server/players/moderate")
def moderate(p:Moderation,_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return advanced.moderate(item["id"],p.action,p.player,p.reason)
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))
@app.get("/api/server/plugins")
def plugins(_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return advanced.installed_plugins(item["id"])
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))
@app.get("/api/plugins/search")
def search_plugins(q:str,_:bool=Depends(secured)):
 try:return advanced.plugin_search(q)
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))

@app.get("/api/plugins/{project_id}/versions")
def plugin_versions(project_id:str,game_version:str,_:bool=Depends(secured)):
 try:return advanced.plugin_versions(project_id,game_version)
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))
@app.post("/api/server/plugins")
def add_plugin(p:PluginInstall,_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return advanced.install_plugin(item["id"],p.version_id)
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))
@app.delete("/api/server/plugins/{filename}")
def delete_plugin(filename:str,_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return advanced.remove_plugin(item["id"],filename)
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))


@app.post("/api/server/update")
def update_server(p:ServerUpdate,_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return core.update_server(item["id"],p.version)
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))
@app.post("/api/server/rollback")
def rollback_server(_:bool=Depends(secured)):
 item=current_server()
 if not item:raise HTTPException(404,detail="No server is configured")
 try:return core.rollback_server(item["id"])
 except (core.ManagerError,OSError,ValueError) as e:raise HTTPException(400,detail=str(e))

app.mount("/",StaticFiles(directory=str(Path(__file__).parent/"web"),html=True),name="panel")
class PathPrefixApp:
 def __init__(self,inner):self.inner=inner
 async def __call__(self,scope,receive,send):
  if scope["type"]!="http":await self.inner(scope,receive,send);return
  prefix="/"+load_web_config()["path"];path=scope.get("path","/")
  if path==prefix:
   scope=dict(scope);scope["path"]="/"
  elif path.startswith(prefix+"/"):
   scope=dict(scope);scope["path"]=path[len(prefix):]
  else:
   body=b'{"detail":"Not Found"}'
   await send({"type":"http.response.start","status":404,"headers":[(b"content-type",b"application/json"),(b"content-length",str(len(body)).encode())]})
   await send({"type":"http.response.body","body":body});return
  await self.inner(scope,receive,send)
public_app=PathPrefixApp(app)
