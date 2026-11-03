"""Character credentials from flags, the environment, or a credentials file.

The file is ~/.lotgdcli/credentials (LOTGD_CREDENTIALS overrides it), holding
`user=Name` and `password=...` lines for the default character, plus one `[Name]`
section with a `password=` line per extra character. It's kept owner-only: the folder 0700 and the
file 0600, tightened on read if something loosened them. `lotgd --save-login`
adds or updates one character in it. Explicit values win over LOTGD_USER/LOTGD_PASSWORD, which win over the file.
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


def _parse(text):
    """Parse the credentials file: top-level `user=`/`password=` lines are the default
    character; each `[Name]` section holds another character's `password=` (and may
    repeat `user=Name`). Returns (default_user, {name_lower: [name, password]})."""
    default = None
    chars = {}
    top_user = top_password = None
    section = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
            if section:
                chars.setdefault(section.lower(), [section, None])
            continue
        k, _, v = stripped.partition("=")
        k, v = k.strip().lower(), v.strip()
        if not v:
            continue
        if section:
            if k == "password":
                chars[section.lower()][1] = v
        elif k == "user":
            top_user = v
        elif k == "password":
            top_password = v
    if top_user:
        default = top_user
        entry = chars.setdefault(top_user.lower(), [top_user, None])
        entry[1] = top_password or entry[1]
    elif top_password:
        chars[None] = [None, top_password]  # password with no user: any character (old behavior)
    return default, chars


def _read_file():
    """Return (default_user, characters) from the credentials file (see _parse)."""
    _migrate()
    if not CRED_FILE.is_file():
        return None, {}
    mode = stat.S_IMODE(CRED_FILE.stat().st_mode)
    if mode & 0o077:
        try:
            os.chmod(CRED_FILE, 0o600)
            _warn(f"{CRED_FILE} was readable by others ({mode:o}); tightened it to 600")
        except OSError:
            _warn(f"{CRED_FILE} is readable by others ({mode:o}); run: chmod 600 {CRED_FILE}")
    return _parse(CRED_FILE.read_text(encoding="utf-8"))


def _format(default, chars):
    out = []
    if default and default.lower() in chars:
        name, password = chars[default.lower()]
        out += [f"user={name}", f"password={password}"]
    for key, (name, password) in chars.items():
        if key is None or (default and key == default.lower()) or not password:
            continue
        out += ["", f"[{name}]", f"password={password}"]
    return "\n".join(out) + "\n"


def save_credentials(user, password):
    """Add or update one character in the file. Other characters are kept; the first
    character saved (or the existing default) stays the default."""
    default, chars = _read_file()
    chars.pop(None, None)
    chars[user.lower()] = [user, password]
    _write_private(CRED_FILE, _format(default or user, chars))
    return CRED_FILE


def saved_characters():
    """Names of the characters with a saved password (no passwords), default first."""
    default, chars = _read_file()
    names = [name for key, (name, pw) in chars.items() if key is not None and pw]
    names.sort(key=lambda n: (not default or n.lower() != default.lower(), n.lower()))
    return names


def load_credentials(user=None, password=None):
    """Return (user, password); either may be None. With no user, use LOTGD_USER, then the
    file's default character. A saved password is only used for the character it was
    saved for, so `-u Other` never sends one character's password while logging in as
    another."""
    user = user or os.environ.get("LOTGD_USER") or None
    password = password or os.environ.get("LOTGD_PASSWORD") or None
    default, chars = _read_file()
    if not user:
        user = default
    if not password:
        entry = chars.get(user.lower()) if user else None
        if entry and entry[1]:
            password = entry[1]
        elif None in chars:  # old file with a password but no user line
            password = chars[None][1]
    return user, password
