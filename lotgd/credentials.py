"""Character credentials from flags, the environment, or a credentials file.

The file is ~/.lotgdcli/credentials (LOTGD_CREDENTIALS overrides it), holding
`user=Name` and `password=...` lines. It's kept owner-only: the folder 0700 and the
file 0600, tightened on read if something loosened them. `lotgd --save-login`
writes it. Explicit values win over LOTGD_USER/LOTGD_PASSWORD, which win over the file.
"""

import os
import stat
import sys
from pathlib import Path

from .paths import HOME_DIR

CRED_FILE = Path(os.environ.get("LOTGD_CREDENTIALS") or HOME_DIR / "credentials").expanduser()
OLD_CRED_FILE = Path("~/.config/lotgdcli/credentials").expanduser()  # before 0.3.0


def _warn(msg):
    print(f"lotgdcli: {msg}", file=sys.stderr)


def _secure_dir(d):
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    if d == HOME_DIR and stat.S_IMODE(d.stat().st_mode) & 0o077:
        os.chmod(d, 0o700)


def _write_private(path, text):
    """Write text to path as 0600 from the start, so it's never readable by others."""
    _secure_dir(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(tmp, 0o600)  # in case tmp already existed with looser bits
    os.replace(tmp, path)


def _migrate():
    """Move the old ~/.config/lotgdcli/credentials here, leaving one copy."""
    if CRED_FILE.exists() or not OLD_CRED_FILE.is_file() or "LOTGD_CREDENTIALS" in os.environ:
        return
    try:
        _write_private(CRED_FILE, OLD_CRED_FILE.read_text(encoding="utf-8"))
        OLD_CRED_FILE.unlink()
        try:
            OLD_CRED_FILE.parent.rmdir()  # only if now empty
        except OSError:
            pass
        _warn(f"moved credentials from {OLD_CRED_FILE} to {CRED_FILE}")
    except OSError as e:
        _warn(f"couldn't move {OLD_CRED_FILE} to {CRED_FILE}: {e}")


def _read_file():
    user = password = None
    _migrate()
    if CRED_FILE.is_file():
        mode = stat.S_IMODE(CRED_FILE.stat().st_mode)
        if mode & 0o077:
            try:
                os.chmod(CRED_FILE, 0o600)
                _warn(f"{CRED_FILE} was readable by others ({mode:o}); tightened it to 600")
            except OSError:
                _warn(f"{CRED_FILE} is readable by others ({mode:o}); run: chmod 600 {CRED_FILE}")
        for line in CRED_FILE.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k == "user" and v:
                user = v
            elif k == "password" and v:
                password = v
    return user, password


def save_credentials(user, password):
    _write_private(CRED_FILE, f"user={user}\npassword={password}\n")
    return CRED_FILE


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
