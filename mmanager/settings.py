import os
from pathlib import Path
ROOT=Path(os.environ.get("MMANAGER_ROOT","/var/lib/mmanager"))
SERVERS=ROOT/"servers"; BACKUPS=ROOT/"backups"
CONFIG=Path(os.environ.get("MMANAGER_CONFIG","/etc/mmanager"))
AUTH_FILE=CONFIG/"auth.json"; TOKEN_FILE=CONFIG/"api.token"
