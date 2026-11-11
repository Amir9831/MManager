# Development operations

These unit files are reference examples, not installed by the current preflight script. Create the `mmanager` system account, install the virtual environment under `/opt/mmanager/venv`, and create state/log directories with ownership assigned to that account before enabling units.

The API binds to loopback port 8765 and the static panel binds to loopback port 8766. For a remote preview, forward both ports:
```bash
ssh -L 8765:127.0.0.1:8765 -L 8766:127.0.0.1:8766 user@server
```
Then open `http://127.0.0.1:8766`. This is a development preview, not an authenticated production deployment.
