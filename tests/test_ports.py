import pytest
from mmanager import ports

def test_preferred_port_is_used_when_available(monkeypatch):
    monkeypatch.setattr(ports, "is_available", lambda port, protocol, host="0.0.0.0": port == 25565)
    assert ports.choose_port(25565, "tcp") == 25565

def test_reserved_port_is_never_selected(monkeypatch):
    monkeypatch.setattr(ports, "is_available", lambda port, protocol, host="0.0.0.0": True)
    selected = ports.choose_port(25565, "tcp", reserved={25565}, attempts=3)
    assert selected != 25565

def test_exhausted_port_search_has_actionable_error(monkeypatch):
    monkeypatch.setattr(ports, "is_available", lambda port, protocol, host="0.0.0.0": False)
    with pytest.raises(ports.PortAllocationError, match="No free TCP port"):
        ports.choose_port(25565, "tcp", attempts=2)
