"""MCP server: lets an agent play LoTGD through the same client and parser as the REPL.

One game session lives for the life of the server process. Credentials come from
the environment or a credentials file, never from tool arguments, so the password
doesn't pass through the model.
"""

import datetime
import fcntl
import json
import os
import re
import threading
import time
from urllib.parse import urlparse

from mcp.server.mcpserver import MCPServer

from .client import DEFAULT_URL, Client
from .credentials import CRED_FILE, load_credentials, saved_characters
from .paths import CACHE_DIR

# Keep it polite: at most one request per MIN_INTERVAL seconds, and a hard cap on
# requests per local calendar day so a runaway agent loop can't hammer the server.
# The day's count lives in CACHE_DIR, shared by every lotgd-mcp process and kept
# across restarts, so reconnecting doesn't reset it.
MIN_INTERVAL = float(os.environ.get("LOTGD_MIN_INTERVAL", "1.5"))
MAX_REQUESTS = int(os.environ.get("LOTGD_MAX_REQUESTS", "2000"))
COUNT_FILE = CACHE_DIR / "requests.json"

INSTRUCTIONS = """\
Play Legend of the Green Dragon (LoTGD) on a real, shared web server.
Start with lotgd_login (or lotgd_look to browse logged out); pass character="Name"
to play one of several saved characters. Every tool returns the
resulting page: its text, the menu, any forms, and the character's stats.
Pick menu entries with lotgd_choose using the hotkey shown in brackets, e.g. "F"
for [F], or "#n" for numbered entries, including [#n] links in the page text
such as shop items. Fill forms with lotgd_submit. Only choose options the
current page offers. Before stopping, log out in the game (e.g. "Quit to the fields")."""

mcp = MCPServer("lotgd", instructions=INSTRUCTIONS)
_lock = threading.Lock()
_client = None
_requests = 0  # today's count (all processes), as of this process's last request
_last = 0.0
_game = None  # the game page to go back to while the mail popup is open
_user = None  # character logged in as


def _get_client():
    global _client
    if _client is None:
        _client = Client(os.environ.get("LOTGD_URL", DEFAULT_URL), os.environ.get("LOTGD_DEBUG") or None)
    return _client


def _count(bump=False):
    """Today's request count from COUNT_FILE (all processes), +1 if bump. Uses a file
    lock so concurrent servers don't lose counts; a new day starts again at 0."""
    global _requests
    today = datetime.date.today().isoformat()
    COUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COUNT_FILE, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        try:
            data = json.loads(fh.read() or "{}")
        except ValueError:
            data = {}
        n = data.get("count", 0) if data.get("date") == today else 0
        if bump:
            n += 1
            fh.seek(0)
            fh.truncate()
            json.dump({"date": today, "count": n}, fh)
    _requests = n
    return n


def _request(fn, *args):
    """Run one server request under the rate limit and daily request cap."""
    global _last
    if _count() >= MAX_REQUESTS:
        raise RuntimeError(f"daily request cap reached ({MAX_REQUESTS} today, LOTGD_MAX_REQUESTS); "
                           "stop playing and tell the user")
    wait = _last + MIN_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    try:
        return fn(*args)
    finally:
        _count(bump=True)
        _last = time.monotonic()


def _is_logout(nav):
    """True for navs that log out on purpose: "Quit to the fields", the inn's room."""
    return "op=logout" in nav.href or bool(re.search(r"\b(quit|log ?out|go to room)\b", nav.label, re.I))


def render(page, note="", check_badnav=True, logout=False):
    """A page as plain text for the model: body, menu, forms, stats.

    check_badnav: warn if this page is the server's badnav.php replay. Pass False
        when re-showing a page without a request, since nothing was rejected.
    logout: the request was a deliberate logout, not a session timeout.
    """
    c = _get_client()
    out = [f"# {page.title or 'LoTGD'}"]
    if note:
        out.append(f"({note})")
    if check_badnav and urlparse(page.url).path.endswith("badnav.php"):
        # the server rejected the nav or a stale form and replayed an earlier page;
        # its text reads as if the action happened again, but nothing changed
        out.append("(WARNING: the server rejected that action and re-showed an earlier page. "
                   "Nothing new happened: no gold spent, no turn used. Don't repeat it; "
                   "pick from the menu below.)")
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
        out.append("- buttons: " + ", ".join(repr(b[2]) for b in form.buttons))
    stats = []
    for label, value in page.stats:
        if not value:
            continue
        bar = page.bars.get(label)
        if bar and re.match(r"exp", label, re.I):
            pct, color = bar
            value += f" ({pct}% to next level" + (", READY to fight your master" if color == "blue" or pct >= 100 else "") + ")"
        kind = {"weapon": "weapon", "armor": "armor"}.get(label.lower())
        lvl = c.gear_level(kind, value) if kind else None
        if lvl:
            value += f" (level {lvl[0]}/{lvl[1]}" + (", best in shop" if lvl[0] >= lvl[1] else "") + ")"
        stats.append(f"{label}: {value}")
    if page.mail:
        stats.append(f"Mail: {page.mail[0]} new, {page.mail[1]} old")
    if _game is not None:
        out.append("\n(In the mail popup. lotgd_mail('close') returns to the game page.)")
    if stats:
        out += ["", "## Stats", "; ".join(stats)]
    if c.logged_in and c.is_logged_out(page):
        c.logged_in = False
        if logout:
            out.append("\n(Logged out. Call lotgd_login to play again.)")
        else:
            out.append("\n(You've been logged out, probably a session timeout. Call lotgd_login.)")
    out.append(f"\n[requests today: {_count()}/{MAX_REQUESTS}]")
    return "\n".join(out)


@mcp.tool()
def lotgd_login(character: str | None = None) -> str:
    """Log in with a saved character. Returns the first in-game page.

    character: name of a character saved in the credentials file (`lotgd --save-login
        -u Name`). Omit it for the default character (LOTGD_USER or the file's `user=`).
        Only the name goes through here; the password comes from the file/environment.
    """
    global _user
    user, password = load_credentials(character or None)
    if not (user and password):
        names = saved_characters()
        who = f"for {character!r} " if character else ""
        saved = f" Saved characters: {', '.join(names)}." if names else ""
        return (f"No credentials configured {who}(nothing was sent).{saved} Ask the user to run "
                f"`lotgd --save-login -u Name` (saves {CRED_FILE}, owner-only), or set LOTGD_USER/LOTGD_PASSWORD.")
    with _lock:
        c = _get_client()
        if c.logged_in:
            if _user and _user.lower() == user.lower():
                return f"Already logged in as {_user}.\n\n" + render(c.page, check_badnav=False)
            return (f"Already logged in as {_user}. Log out in the game first (e.g. \"Quit to the "
                    f"fields\"), then log in as {user}. Nothing was sent.")
        if not c.page:
            _request(c.home)
        page = _request(c.login, user, password)
        if not c.logged_in:
            return render(page, "LOGIN FAILED: check the configured credentials", check_badnav=False)
        _user = user
        return render(page, f"logged in as {user}", check_badnav=False)


@mcp.tool()
def lotgd_look() -> str:
    """Show the current page again without contacting the server (loads the
    logged-out home page if nothing is loaded yet)."""
    with _lock:
        c = _get_client()
        if c.page:
            return render(c.page, check_badnav=False)
        return render(_request(c.home))


@mcp.tool()
def lotgd_choose(choice: str) -> str:
    """Follow a menu entry or in-text link on the current page.

    choice: the hotkey letter shown in brackets ("F" for [F] Forest), "#n" for a
    numbered entry or in-text link ("#4"; a bare "4" works too unless 4 is a
    hotkey), or the entry's exact label.
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
            if not nav and m:  # "4" or "[4]" with no hotkey 4: treat it as "#4"
                n = int(m[1])
                nav = page.navs[n - 1] if 1 <= n <= len(page.navs) else None
        if not nav:
            return f"No entry {choice!r} on this page; nothing was sent.\n\n" + render(page, check_badnav=False)
        return render(_request(c.get, nav.href), f"chose: {nav.label}", logout=_is_logout(nav))


@mcp.tool()
def lotgd_submit(form: int = 1, values: dict[str, str | int | float | bool] | None = None,
                 button: str | None = None) -> str:
    """Fill in and submit a form on the current page (bank, inn, chat, naming...).

    form: form number as listed under "## Form n".
    values: field name -> value. Fields you leave out keep their defaults. For
        select/radio fields give the option value or its label (any case); for
        checkboxes "on"/"off" or true/false.
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
            if given is not None:
                given = str(given)  # agents often send numbers/booleans as JSON, not strings
            if fld.kind == "password":
                return "This form wants a password; use lotgd_login instead. Nothing was sent."
            if given is None:
                if fld.kind != "checkbox" or fld.value:
                    data[fld.name] = fld.value
                continue
            if fld.kind in ("select", "radio"):
                match = next((v for v, l in fld.options if given in (v, l)), None)
                if match is None:  # "deposit" for "Deposit"
                    match = next((v for v, l in fld.options if given.lower() in (v.lower(), l.lower())), None)
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
            btn = next((b for b in f.buttons if b[2].lower() == button.lower()), None)
            if not btn:
                return f"No button {button!r}; buttons are {[b[2] for b in f.buttons]}. Nothing was sent."
        return render(_request(c.submit, f, data, btn), f"submitted form {form}")


@mcp.tool()
def lotgd_mail(action: str = "open") -> str:
    """Open or close Ye Olde Mail (the in-game mailbox popup).

    action: "open" shows the inbox; then use lotgd_choose for the [#n] links
        (read a message, Write, Reply) and lotgd_submit for its forms.
        "close" goes back to the game page you were on (no request needed;
        its menu still works).
    """
    global _game
    with _lock:
        c = _get_client()
        if action == "close":
            if _game is None:
                if c.page:
                    return "Mail isn't open.\n\n" + render(c.page, check_badnav=False)
                return "Mail isn't open.\n\n" + render(_request(c.home))
            c.page, _game = _game, None
            return render(c.page, "closed mail, back in the game", check_badnav=False)
        if not c.logged_in:
            return "Not logged in; call lotgd_login first."
        game = _game if _game is not None else c.page
        page = _request(c.mail)
        _game = None if c.is_logged_out(page) else game
        return render(page, "opened mail")


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
