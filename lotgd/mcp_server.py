"""MCP server: lets an agent play LoTGD through the same client and parser as the REPL.

One game session lives for the life of the server process. Credentials come from
the environment or a credentials file, never from tool arguments, so the password
doesn't pass through the model.
"""

import os
import re
import threading
import time
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from .client import DEFAULT_URL, Client

CRED_FILE = Path(os.environ.get("LOTGD_CREDENTIALS", "~/.config/lotgdcli/credentials")).expanduser()
# Keep it polite: at most one request per MIN_INTERVAL seconds, and a hard cap on
# requests per server process so a runaway agent loop can't hammer the server.
MIN_INTERVAL = float(os.environ.get("LOTGD_MIN_INTERVAL", "1.5"))
MAX_REQUESTS = int(os.environ.get("LOTGD_MAX_REQUESTS", "300"))

INSTRUCTIONS = """\
Play Legend of the Green Dragon (LoTGD) on a real, shared web server.
Start with lotgd_login (or lotgd_look to browse logged out). Every tool returns the
resulting page: its text, the menu, any forms, and the character's stats.
Pick menu entries with lotgd_choose using the hotkey shown in brackets, e.g. "F"
for [F], or "#n" for numbered entries, including [#n] links in the page text
such as shop items. Fill forms with lotgd_submit. Only choose options the
current page offers. Before stopping, log out in the game (e.g. "Quit to the fields")."""

mcp = MCPServer("lotgd", instructions=INSTRUCTIONS)
_lock = threading.Lock()
_client = None
_requests = 0
_last = 0.0


def _creds():
    user, password = os.environ.get("LOTGD_USER"), os.environ.get("LOTGD_PASSWORD")
    if CRED_FILE.is_file():
        for line in CRED_FILE.read_text().splitlines():
            k, _, v = line.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k == "user" and not user:
                user = v
            elif k == "password" and not password:
                password = v
    return user, password


def _get_client():
    global _client
    if _client is None:
        _client = Client(os.environ.get("LOTGD_URL", DEFAULT_URL), os.environ.get("LOTGD_DEBUG") or None)
    return _client


def _request(fn, *args):
    """Run one server request under the rate limit and request cap."""
    global _requests, _last
    if _requests >= MAX_REQUESTS:
        raise RuntimeError(f"request cap reached ({MAX_REQUESTS} this session, LOTGD_MAX_REQUESTS); "
                           "stop playing and tell the user")
    wait = _last + MIN_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    try:
        return fn(*args)
    finally:
        _requests += 1
        _last = time.monotonic()


def render(page, note=""):
    """A page as plain text for the model: body, menu, forms, stats."""
    c = _get_client()
    out = [f"# {page.title or 'LoTGD'}"]
    if note:
        out.append(f"({note})")
    out += ["", page.body.plain.strip(), "", "## Menu"]
    section = None
    for i, nav in enumerate(page.navs, 1):
        if nav.inline:
            continue  # shown as [#n] in the body text
        if nav.section != section:
            section = nav.section
            if section:
                out.append(f"-- {section} --")
        label = re.sub(r"^\(.\)\s*", "", nav.label)  # jade repeats the hotkey: "(V) Return..."
        out.append(f"[{nav.key.upper() if nav.key else '#' + str(i)}] {label}")
    inline = sum(n.inline for n in page.navs)
    if inline:
        out.append(f"(+{inline} in-text links marked [#n] above)")
    for n, form in enumerate(page.forms, 1):
        out.append(f"\n## Form {n}")
        for f in form.fields:
            if f.kind == "hidden":
                continue
            desc = f"- {f.name} ({f.kind})"
            if f.label:
                desc += f" '{f.label}'"
            if f.options:
                desc += " options: " + ", ".join(f"{v!r}={l!r}" for v, l in f.options)
            if f.value:
                desc += f" default={f.value!r}"
            out.append(desc)
        out.append("- buttons: " + ", ".join(repr(b[1]) for b in form.buttons))
    stats = []
    for label, value in page.stats:
        if not value:
            continue
        bar = page.bars.get(label)
        if bar and re.match(r"exp", label, re.I):
            pct, color = bar
            value += f" ({pct}% to next level" + (", READY to fight your master" if color == "blue" or pct >= 100 else "") + ")"
        stats.append(f"{label}: {value}")
    if stats:
        out += ["", "## Stats", "; ".join(stats)]
    if c.logged_in and c.is_logged_out(page):
        c.logged_in = False
        out.append("\n(You've been logged out, probably a session timeout. Call lotgd_login.)")
    out.append(f"\n[requests this session: {_requests}/{MAX_REQUESTS}]")
    return "\n".join(out)


@mcp.tool()
def lotgd_login() -> str:
    """Log in with the character configured for this server (LOTGD_USER/LOTGD_PASSWORD
    or the credentials file). Returns the first in-game page."""
    user, password = _creds()
    if not (user and password):
        return (f"No credentials configured. Ask the user to put 'user=Name' and 'password=...' "
                f"lines in {CRED_FILE} (chmod 600), or set LOTGD_USER/LOTGD_PASSWORD.")
    with _lock:
        c = _get_client()
        if not c.page:
            _request(c.home)
        page = _request(c.login, user, password)
        if not c.logged_in:
            return render(page, "LOGIN FAILED: check the configured credentials")
        return render(page, f"logged in as {user}")


@mcp.tool()
def lotgd_look() -> str:
    """Show the current page again without contacting the server (loads the
    logged-out home page if nothing is loaded yet)."""
    with _lock:
        c = _get_client()
        return render(c.page or _request(c.home))


@mcp.tool()
def lotgd_choose(choice: str) -> str:
    """Follow a menu entry or in-text link on the current page.

    choice: the hotkey letter shown in brackets ("F" for [F] Forest), "#n" for a
    numbered entry or in-text link ("#4"), or the entry's exact label.
    """
    with _lock:
        c = _get_client()
        page = c.page or _request(c.home)
        choice = choice.strip()
        nav = None
        m = re.fullmatch(r"\[?#?(\d+)\]?", choice)
        if m and choice.lstrip("[").startswith("#"):
            n = int(m[1])
            nav = page.navs[n - 1] if 1 <= n <= len(page.navs) else None
        else:
            key = choice.strip("[]")
            if len(key) == 1:
                nav = next((n for n in page.navs if n.key and n.key.lower() == key.lower()), None)
            if not nav:
                hits = [n for n in page.navs
                        if re.sub(r"^\(.\)\s*", "", n.label).lower() == choice.lower() or n.label.lower() == choice.lower()]
                nav = hits[0] if len(hits) == 1 else None
        if not nav:
            return f"No entry {choice!r} on this page; nothing was sent.\n\n" + render(page)
        return render(_request(c.get, nav.href), f"chose: {nav.label}")


@mcp.tool()
def lotgd_submit(form: int = 1, values: dict[str, str] | None = None, button: str | None = None) -> str:
    """Fill in and submit a form on the current page (bank, inn, chat, naming...).

    form: form number as listed under "## Form n".
    values: field name -> value. Fields you leave out keep their defaults. For
        select/radio fields give the option value or its label; for checkboxes
        "on"/"off".
    button: label of the button to press (default: the first one).
    """
    with _lock:
        c = _get_client()
        if not c.page or not 1 <= form <= len(c.page.forms):
            return "No such form on this page; nothing was sent."
        f = c.page.forms[form - 1]
        values = dict(values or {})
        data = {}
        for fld in f.fields:
            given = values.pop(fld.name, None)
            if fld.kind == "password":
                return "This form wants a password; use lotgd_login instead. Nothing was sent."
            if given is None:
                if fld.kind != "checkbox" or fld.value:
                    data[fld.name] = fld.value
                continue
            if fld.kind in ("select", "radio"):
                match = next((v for v, l in fld.options if given in (v, l)), None)
                if match is None:
                    return f"{given!r} isn't an option for {fld.name}; nothing was sent."
                data[fld.name] = match
            elif fld.kind == "checkbox":
                if given.lower() in ("on", "yes", "true", "1", fld.options[0][0]):
                    data[fld.name] = fld.options[0][0]
            else:
                data[fld.name] = given
        if values:
            return f"Unknown field(s) {sorted(values)}; nothing was sent."
        btn = f.buttons[0]
        if button:
            btn = next((b for b in f.buttons if b[1].lower() == button.lower()), None)
            if not btn:
                return f"No button {button!r}; buttons are {[b[1] for b in f.buttons]}. Nothing was sent."
        return render(_request(c.submit, f, data, btn), f"submitted form {form}")


@mcp.tool()
def lotgd_reload() -> str:
    """Reload the current page from the server (e.g. to refresh chat or the new-day timer)."""
    with _lock:
        c = _get_client()
        if not c.page:
            return render(_request(c.home))
        return render(_request(c.get, c.page.url))


def main():
    mcp.run()


if __name__ == "__main__":
    main()
