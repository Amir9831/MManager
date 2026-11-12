import random,socket
class PortAllocationError(RuntimeError): pass
def is_available(port,protocol="tcp",host="0.0.0.0"):
 if protocol not in {"tcp","udp"}: raise ValueError("protocol must be tcp or udp")
 if not 1<=int(port)<=65535: return False
 kind=socket.SOCK_STREAM if protocol=="tcp" else socket.SOCK_DGRAM
 with socket.socket(socket.AF_INET,kind) as s:
  try: s.bind((host,int(port))); return True
  except OSError: return False
def choose_port(preferred,protocol,reserved=None,low=20000,high=50000,attempts=128):
 if protocol not in {"tcp","udp","tcp+udp"} or not 1<=low<=high<=65535: raise ValueError("invalid port configuration")
 reserved=reserved or set()
 protocols=("tcp","udp") if protocol=="tcp+udp" else (protocol,)
 for p in [preferred]+[random.randint(low,high) for _ in range(attempts)]:
  if p not in reserved and all(is_available(p,proto) for proto in protocols): return p
 raise PortAllocationError(f"No free {protocol.upper()} port after {attempts+1} attempts")
