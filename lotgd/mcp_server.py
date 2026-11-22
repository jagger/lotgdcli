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
        out.append(f"\n## Form {n}" + (f" (posts to {form.action.split('?')[0]}"
                                      + (f", {re.search(r'op=(\\w+)', form.action)[0]}" if re.search(r'op=\w+', form.action or '') else "")
                                      + ")" if form.action else ""))
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
            value += f" ({pct}% to next level" + (", READY to fight your master" if color == "blue" else "") + ")"
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
                 button: str | None = None, expect: str | None = None) -> str:
    """Fill in and submit a form on the current page (bank, inn, chat, naming...).

    form: form number as listed under "## Form n".
    values: field name -> value. Fields you leave out keep their defaults. For
        select/radio fields give the option value or its label (any case); for
        checkboxes "on"/"off" or true/false.
    button: label of the button to press (default: the first one).
    expect: text the form's target must contain (e.g. "bank.php"). Form numbers can
        shift between page loads, so pass it to refuse a submit to the wrong form.
    """
    with _lock:
        c = _get_client()
        if not c.page or not 1 <= form <= len(c.page.forms):
            return "No such form on this page; nothing was sent."
        f = c.page.forms[form - 1]
        if expect and expect.lower() not in (f.action or "").lower():
            return (f"Form {form} posts to {f.action!r}, not {expect!r}; nothing was sent. "
                    "Form numbers shift between page loads: check the list below.\n\n"
                    + render(c.page, check_badnav=False))
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
        if c.from_post:
            # this page answered a form POST; fetching its URL would replay the form
            # without its data and the server answers badnav. Nothing is sent.
            return ("This page came from a form submission, so it can't be reloaded without "
                    "replaying the form (nothing was sent). Pick a menu entry instead.\n\n"
                    + render(c.page, check_badnav=False))
        return render(_request(c.get, c.page.url))


def _num(text):
    m = re.search(r"-?\d[\d,]*", text or "")
    return int(m[0].replace(",", "")) if m else None


def stat_dict(page):
    """The page's stats as {label: value}; the first of a repeated label wins."""
    out = {}
    for label, value in page.stats:
        out.setdefault(label, value)
    return out


def status_of(page):
    """Character status from a page's stats sidebar, as plain data (no request)."""
    st = stat_dict(page)
    hp = re.match(r"\s*(\d[\d,]*)\s*/\s*(\d[\d,]*)", st.get("Hitpoints", ""))
    xp = next((b for k, b in page.bars.items() if re.match(r"exp", k, re.I)), None)
    out = {"page": page.title, "name": st.get("Name"), "level": _num(st.get("Level")),
           "hp": int(hp[1].replace(",", "")) if hp else None,
           "max_hp": int(hp[2].replace(",", "")) if hp else None,
           "xp": _num(st.get("Experience")), "xp_pct_to_next": xp[0] if xp else None,
           "ready_for_master": bool(xp and xp[1] == "blue"),
           "turns": _num(st.get("Turns")), "pvp_fights": _num(st.get("PvP")),
           "gold": _num(st.get("Gold")), "bank": _num(st.get("Bankgold")), "gems": _num(st.get("Gems")),
           "favor": _num(st.get("Favor")), "spirits": st.get("Spirits"),
           "weapon": st.get("Weapon"), "armor": st.get("Armor"), "buffs": st.get("Buffs")}
    if page.mail:
        out["mail_new"] = page.mail[0]
    return {k: v for k, v in out.items() if v is not None}


@mcp.tool()
def lotgd_status() -> str:
    """Compact character status as JSON (level, XP, HP, gold, bank, gems, turns, PvP,
    favor, buffs, requests used today). Reads the stats of the current page, so it
    sends no request; refresh them by visiting a page first."""
    with _lock:
        c = _get_client()
        if not c.page or not c.logged_in:
            return "Not logged in; call lotgd_login first."
        data = status_of(c.page)
        data["requests_today"] = _count()
        data["request_cap"] = MAX_REQUESTS
        return json.dumps(data, indent=1, ensure_ascii=False)


def _nav(page, pattern, label=False):
    """First menu entry whose href (or label) matches the regex, or None."""
    return next((n for n in page.navs if re.search(pattern, n.label if label else n.href, re.I)), None)


@mcp.tool()
def lotgd_bank(action: str = "balance", amount: int | str | None = None, keep: int = 0,
               return_to_village: bool = True) -> str:
    """Deposit or withdraw gold at the bank in one call. Start from the village (or
    anywhere with a bank link, or the bank itself).

    action: "balance" (no request), "deposit" or "withdraw".
    amount: gold to move; omit or "all" to deposit everything on hand (minus keep)
        or withdraw the whole balance. Clamped to what you have.
    keep: with "deposit", gold to leave on hand (e.g. keep=100 for the healer).
    return_to_village: go back to the village afterwards (one more request).
    """
    action = (action or "").strip().lower()
    with _lock:
        c = _get_client()
        if not c.page or not c.logged_in:
            return "Not logged in; call lotgd_login first."
        st = status_of(c.page)
        gold, bank = st.get("gold"), st.get("bank")
        if action == "balance":
            return f"Gold on hand {gold}, in bank {bank} (from the current page; nothing was sent)."
        if action not in ("deposit", "withdraw"):
            return f"Unknown action {action!r}; use balance, deposit or withdraw. Nothing was sent."
        if gold is None or bank is None:
            return "This page shows no gold/bank stats; go to the village first. Nothing was sent."
        have = gold if action == "deposit" else bank
        whole = amount is None or str(amount).strip().lower() == "all"
        try:
            n = max(have - max(keep, 0), 0) if whole and action == "deposit" else have if whole else int(amount)
        except ValueError:
            return f"amount {amount!r} isn't a number; nothing was sent."
        n = min(n, have)
        if n <= 0:
            return f"Nothing to {action} (gold {gold}, bank {bank}, keep {keep}). Nothing was sent."
        page = c.page
        if not _nav(page, rf"bank\.php\?op={action}"):
            go = _nav(page, r"^bank\.php(\?c=|$)")
            if not go:
                return "No bank link on this page; go to the village first. Nothing was sent."
            page = _request(c.get, go.href)
        step = _nav(page, rf"bank\.php\?op={action}")
        if not step:
            return "The bank page has no such option.\n\n" + render(page, check_badnav=False)
        page = _request(c.get, step.href)
        form = next((f for f in page.forms if "bank.php" in (f.action or "")), None)
        field = next((x for x in (form.fields if form else []) if x.kind == "text"), None)
        if not field:
            return "The bank form wasn't found.\n\n" + render(page, check_badnav=False)
        page = _request(c.submit, form, {field.name: str(n)}, form.buttons[0])
        lines = [x.strip() for x in page.body.plain.split("\n") if x.strip()]
        ledger = next((x for x in lines if re.search(r"gold", x)), lines[0] if lines else "")[:300]
        if return_to_village:
            back = _nav(page, r"^village\.php")
            if back:
                page = _request(c.get, back.href)
        after = status_of(page)
        return render(page, f"{action} {n}: {ledger} -> gold {after.get('gold')}, bank {after.get('bank')}",
                      check_badnav=False)


def pick_heal(hp, max_hp, target_pct, options):
    """Smallest potion that gets to target_pct of max HP. options: {pct: cost or None}.

    Percent potions heal that percent of the *missing* HP. Returns (pct, cost) or None."""
    want = -(-target_pct * max_hp // 100)  # ceil
    missing = max_hp - hp
    if missing <= 0 or want <= hp:
        return None
    need = (want - hp) * 100 / missing
    for pct in sorted(options):
        if pct >= need - 1e-9:
            return pct, options[pct]
    return None


@mcp.tool()
def lotgd_heal(target_pct: int = 100) -> str:
    """Buy the cheapest healing potion that brings HP to at least target_pct of max HP
    (default 100). Start from the village, the forest or the healer's hut. Sends no
    request if HP is already high enough, and won't buy if the price is more than the
    gold on hand."""
    with _lock:
        c = _get_client()
        if not c.page or not c.logged_in:
            return "Not logged in; call lotgd_login first."
        st = status_of(c.page)
        hp, max_hp, gold = st.get("hp"), st.get("max_hp"), st.get("gold")
        if hp is None or max_hp is None:
            return "This page shows no HP; nothing was sent."
        target_pct = min(max(int(target_pct), 1), 100)
        if hp * 100 >= target_pct * max_hp:
            return f"HP {hp}/{max_hp} is already at {target_pct}% or more; nothing was sent."
        page = c.page
        if not _nav(page, r"healer\.php\?op=buy"):
            go = _nav(page, r"^healer\.php(\?c=|$)")
            if not go:
                return "No healer link on this page; go to the village or forest first. Nothing was sent."
            page = _request(c.get, go.href)
        options = {}
        for n in page.navs:
            m = re.search(r"healer\.php\?op=buy&pct=(\d+)", n.href)
            if m:
                options[int(m[1])] = _num(re.sub(r"^.*?-", "", n.label)) if "gold" in n.label else None
        hp2, max2 = status_of(page).get("hp", hp), status_of(page).get("max_hp", max_hp)
        pick = pick_heal(hp2, max2, target_pct, options)
        if not pick:
            return "No healing potion on offer reaches that.\n\n" + render(page, check_badnav=False)
        pct, cost = pick
        if cost is not None and gold is not None and cost > gold:
            return (f"The {pct}% potion costs {cost} gold but you have {gold}; nothing was bought.\n\n"
                    + render(page, check_badnav=False))
        nav = _nav(page, rf"healer\.php\?op=buy&pct={pct}\b")
        page = _request(c.get, nav.href)
        after = status_of(page)
        return render(page, f"bought the {pct}% potion" + (f" for {cost} gold" if cost else "")
                      + f": HP {after.get('hp')}/{after.get('max_hp')}, gold {after.get('gold')}",
                      check_badnav=False)


def _label(nav):
    return re.sub(r"^\(.\)\s*", "", nav.label).strip()


def farm_action(page, fairy="decline"):
    """What the forest-farm loop should do on this page, as (kind, nav).

    kinds: "fairy" (decline/accept the gem fairy), "fight" (press Fight),
    "forest" (nav is a (look, thrill) pair of navs), "unknown" (stop and tell the user).
    Only these forest actions are ever chosen: no PvP, chat, mail or shopping.
    """
    labels = {_label(n).lower(): n for n in page.navs}
    gem = labels.get("give her a gem" if fairy == "accept" else "don't give her a gem")
    if gem:
        return "fairy", gem
    if "fight" in labels and "run" in labels:
        return "fight", labels["fight"]
    look = next((n for k, n in labels.items() if k.startswith("look for something to kill")), None)
    thrill = next((n for k, n in labels.items() if "thrillseeking" in k), None)
    if look and thrill:
        return "forest", (look, thrill)
    return "unknown", None


@mcp.tool()
def lotgd_farm(kills: int = 20, mode: str = "look", fairy: str = "decline",
               heal_below_pct: int = 60, max_requests: int = 120) -> str:
    """Run the forest-fight loop for you and return only a short summary.

    Start from the forest menu (or the healer's hut). Repeats: Look for Something to
    Kill (mode "look"), Go Thrillseeking ("thrill"), or every third fight a thrill
    ("mix"), then presses Fight until the fight ends. Heals at the healer when HP is
    below heal_below_pct (stops if it can't afford the potion). The gem fairy is
    declined (fairy="decline") or accepted ("accept"). It stops when `kills` fights are
    won, max_requests requests are used (about 1.5 s each), the daily cap is near, HP
    drops below 25% mid-fight, you die, or any page it doesn't recognise. It never
    runs from a fight, buys gear, banks, chats, mails or attacks players. It obeys the
    same rate limit and daily cap as every other tool."""
    with _lock:
        c = _get_client()
        if not c.page or not c.logged_in:
            return "Not logged in; call lotgd_login first."
        start = status_of(c.page)
        used0, won, fairies, heals, thrills, step = _count(), 0, 0, 0, 0, 0
        stop = "finished"
        kills = max(1, min(int(kills), 500))
        mode = mode if mode in ("look", "thrill", "mix") else "look"
        heal_below_pct = min(max(int(heal_below_pct), 10), 95)
        while won < kills:
            page = c.page
            st = status_of(page)
            if _count() - used0 >= max_requests:
                stop = "request budget for this call used up"
                break
            if _count() >= MAX_REQUESTS - 5:
                stop = "daily request cap nearly reached"
                break
            if not c.logged_in or c.is_logged_out(page):
                stop = "logged out"
                break
            if re.search(r"you have been slain|you are dead", page.body.plain, re.I):
                stop = "died"
                break
            hp, mx = st.get("hp"), st.get("max_hp")
            kind, nav = farm_action(page, fairy)
            if kind == "fairy":
                fairies += 1
                _request(c.get, nav.href)
            elif kind == "fight":
                if hp is not None and mx and hp * 100 < 25 * mx:
                    stop = f"HP low mid-fight ({hp}/{mx}); take over"
                    break
                after = _request(c.get, nav.href)
                if re.search(r"you have slain", after.body.plain, re.I):
                    won += 1
            elif kind == "forest":
                if hp is not None and mx and hp * 100 < heal_below_pct * mx:
                    go = _nav(page, r"^healer\.php(\?c=|$)")
                    if not go:
                        stop = "hurt but no healer link on this page"
                        break
                    hpage = _request(c.get, go.href)
                    buy = _nav(hpage, r"healer\.php\?op=buy&pct=100\b")
                    if not buy:
                        stop = "no full-heal option"
                        break
                    cost = _num(re.sub(r"^.*?-", "", buy.label)) if "gold" in buy.label else None
                    if cost and st.get("gold") is not None and cost > st["gold"]:
                        stop = f"full heal costs {cost}, have {st['gold']}"
                        break
                    _request(c.get, buy.href)
                    heals += 1
                    continue
                step += 1
                use_thrill = mode == "thrill" or (mode == "mix" and step % 3 == 0)
                thrills += use_thrill
                _request(c.get, (nav[1] if use_thrill else nav[0]).href)
            else:
                stop = f"unrecognised page {page.title!r}; take over"
                break
        end = status_of(c.page)

        def d(k):
            return (end.get(k) or 0) - (start.get(k) or 0)

        return (f"farm: {stop}. kills {won}, fairies {fairies} ({fairy}), heals {heals}, thrills {thrills}, "
                f"requests {_count() - used0} (today {_count()}/{MAX_REQUESTS}).\n"
                f"gold {start.get('gold')}->{end.get('gold')} ({d('gold'):+}), gems {d('gems'):+}, "
                f"xp {d('xp'):+} (now {end.get('xp')}), hp {end.get('hp')}/{end.get('max_hp')}, "
                f"turns {end.get('turns')}, page {end.get('page')!r}.")


def main():
    mcp.run()


if __name__ == "__main__":
    main()
