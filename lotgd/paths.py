"""Where lotgdcli keeps what it saves: ~/.lotgdcli/cache (LOTGD_HOME overrides ~/.lotgdcli).

Everything the client writes goes under CACHE_DIR: learned gear levels, :raw page
dumps, and --debug logs. Credentials are user-written config and stay where
credentials.py says.
"""

import os
from pathlib import Path

HOME_DIR = Path(os.environ.get("LOTGD_HOME") or "~/.lotgdcli").expanduser()
CACHE_DIR = HOME_DIR / "cache"
DEBUG_DIR = CACHE_DIR / "debug"
RAW_DIR = CACHE_DIR / "raw"
# before 0.3.0 the gear cache lived in the XDG cache dir; read it once to migrate
OLD_CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or "~/.cache").expanduser() / "lotgdcli"
