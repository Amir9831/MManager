from fastapi import FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,Field
from . import store,core
app=FastAPI(title='MManager API',version='0.1.0')
# The API is loopback-only. CORS is limited to the local forwarded panel origins.
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:8766','http://localhost:8766'],allow_credentials=False,allow_methods=['GET','POST','DELETE'],allow_headers=['Content-Type'])
class CreateServer(BaseModel):
 name:str=Field(min_length=2,max_length=32)
 edition:str
 version:str=Field(min_length=1,max_length=40)
@app.get('/api/health')
def health(): return {'status':'ok','version':'0.1.0'}
@app.get('/api/servers')
def servers(): return {'items':store.list_servers()}
@app.post('/api/servers')
def create(p:CreateServer):
 try: return core.create_server(p.name,p.edition,p.version)
 except (core.ManagerError,OSError,ValueError) as e: raise HTTPException(400,detail=str(e))
@app.delete('/api/servers/{sid}')
def delete(sid:str,confirm:bool=False):
 try: return core.delete_server(sid,confirm)
 except core.ManagerError as e: raise HTTPException(400,detail=str(e))
