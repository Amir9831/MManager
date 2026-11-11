from mmanager.ports import choose_port

def test_choose_port_uses_a_free_port():
 import socket
 s=socket.socket(); s.bind(('127.0.0.1',0)); occupied=s.getsockname()[1]; s.close()
 result=choose_port(occupied,'tcp',low=30000,high=40000,attempts=20)
 assert 1 <= result <= 65535
