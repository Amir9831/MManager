from fastapi import FastAPI,HTTPException,Depends,Header,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from .webconfig import load as load_web_config
from pydantic import BaseModel,Field
from . import store,core,auth
app=FastAPI(title="MManager API",version="0.2.0")
app.add_middleware(CORSMiddleware,allow_origins=[],allow_credentials=False,allow_methods=["GET","POST"],allow_headers=["Content-Type","Authorization"])
class Login(BaseModel): password:str=Field(min_length=1,max_length=256)
class CreateServer(BaseModel):
 name:str=Field(min_length=2,max_length=32); edition:str="java"; software:str="vanilla"; version:str=Field(min_length=1,max_length=40); accept_eula:bool=False
def secured(authorization:str|None=Header(default=None)):
 token=authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
 if not auth.verify_token(token): raise HTTPException(401,detail="Authentication required")
 return True
@app.get("/api/health")
def health(): return {"status":"ok","version":"0.2.0"}
@app.post("/api/login")
def login(p:Login,request:Request):
 token=auth.verify_login(p.password,request.client.host if request.client else "unknown")
 if not token: raise HTTPException(401,detail="Invalid credentials or rate limit reached")
 return {"token":token}
@app.get("/api/servers")
def servers(_:bool=Depends(secured)): return {"items":store.list_servers()}
@app.post("/api/servers")
def create(p:CreateServer,_:bool=Depends(secured)):
 try: return core.create_server(p.name,p.edition,p.version,p.software,p.accept_eula)
 except (core.ManagerError,OSError,ValueError) as e: raise HTTPException(400,detail=str(e))
@app.post("/api/servers/{sid}/{action}")
def action(sid:str,action:str,_:bool=Depends(secured)):
 try: return core.server_action(sid,action)
 except core.ManagerError as e: raise HTTPException(400,detail=str(e))
@app.get("/api/servers/{sid}/logs")
def logs(sid:str,lines:int=100,_:bool=Depends(secured)):
 try: return {"logs":core.server_logs(sid,lines)}
 except core.ManagerError as e: raise HTTPException(400,detail=str(e))
@app.post("/api/servers/{sid}/backups")
def backup(sid:str,_:bool=Depends(secured)):
 try: return core.create_backup(sid)
 except (core.ManagerError,OSError) as e: raise HTTPException(400,detail=str(e))
@app.get("/api/servers/{sid}/backups")
def backups(sid:str,_:bool=Depends(secured)):
 try: return {"items":core.list_backups(sid)}
 except core.ManagerError as e: raise HTTPException(400,detail=str(e))
@app.post("/api/servers/{sid}/backups/{bid}/restore")
def restore(sid:str,bid:str,confirm:bool=False,_:bool=Depends(secured)):
 try: return core.restore_backup(sid,bid,confirm)
 except (core.ManagerError,OSError,ValueError) as e: raise HTTPException(400,detail=str(e))

app.mount("/", StaticFiles(directory=str(Path(__file__).parent / "web"), html=True), name="panel")

class PathPrefixApp:
    """Expose the API and static panel only beneath the configured secret path."""
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.inner(scope, receive, send)
            return
        prefix = "/" + load_web_config()["path"]
        path = scope.get("path", "/")
        if path == prefix:
            scope = dict(scope)
            scope["path"] = "/"
        elif path.startswith(prefix + "/"):
            scope = dict(scope)
            scope["path"] = path[len(prefix):]
        else:
            body = b'{"detail":"Not Found"}'
            await send({"type":"http.response.start","status":404,"headers":[(b"content-type",b"application/json"),(b"content-length",str(len(body)).encode())]})
            await send({"type":"http.response.body","body":body})
            return
        await self.inner(scope, receive, send)

public_app = PathPrefixApp(app)
