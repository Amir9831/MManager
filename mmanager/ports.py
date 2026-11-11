import random, socket
class PortAllocationError(RuntimeError): pass
def is_available(port, protocol='tcp', host='0.0.0.0'):
    kind=socket.SOCK_STREAM if protocol.lower()=='tcp' else socket.SOCK_DGRAM
    s=socket.socket(socket.AF_INET,kind)
    try: s.bind((host,port)); return True
    except OSError: return False
    finally: s.close()
def choose_port(preferred, protocol, reserved=None, low=20000, high=50000, attempts=128):
    reserved=reserved or set()
    for p in [preferred]+[random.randint(low,high) for _ in range(attempts)]:
        if p not in reserved and is_available(p,protocol): return p
    raise PortAllocationError(f'No free {protocol.upper()} port after {attempts+1} attempts')
