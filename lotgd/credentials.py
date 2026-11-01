"""Character credentials from flags, the environment, or a credentials file.

The file holds `user=Name` and `password=...` lines (chmod 600). Explicit values
win over LOTGD_USER/LOTGD_PASSWORD, which win over the file.
"""

import os
from pathlib import Path

CRED_FILE = Path(os.environ.get("LOTGD_CREDENTIALS", "~/.config/lotgdcli/credentials")).expanduser()


def _read_file():
    user = password = None
    if CRED_FILE.is_file():
        for line in CRED_FILE.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k == "user" and v:
                user = v
            elif k == "password" and v:
                password = v
    return user, password


def load_credentials(user=None, password=None):
    """Return (user, password); either may be None. The file's password is only
    used for the file's own user (or when the file names no user), so `-u Other`
    doesn't send one character's password while logging in as another."""
    user = user or os.environ.get("LOTGD_USER") or None
    password = password or os.environ.get("LOTGD_PASSWORD") or None
    file_user, file_password = _read_file()
    if not user:
        user = file_user
    if not password and file_password and (not file_user or file_user.lower() == user.lower()):
        password = file_password
    return user, password
