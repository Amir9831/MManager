import json,secrets,time
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError,InvalidHashError
from .settings import AUTH_FILE,TOKEN_FILE
_hasher=PasswordHasher(); _attempts={}
def verify_login(password,client="unknown"):
 now=time.time(); hits=[x for x in _attempts.get(client,[]) if now-x<300]
 if len(hits)>=8: return None
 hits.append(now); _attempts[client]=hits
 try:
  data=json.loads(AUTH_FILE.read_text())
  if _hasher.verify(data["password_hash"],password): return TOKEN_FILE.read_text().strip()
 except (OSError,KeyError,ValueError,VerifyMismatchError,InvalidHashError): pass
 return None
def verify_token(token):
 try: expected=TOKEN_FILE.read_text().strip()
 except OSError: return False
 return bool(token) and secrets.compare_digest(token,expected)
