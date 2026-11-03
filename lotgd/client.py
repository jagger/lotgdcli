"""HTTP session against a LoTGD server."""

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from .parser import parse

DEFAULT_URL = "https://lotgd.popetoad.com/"
SKIN = "legacy:jade.htm"  # parser is written against this skin's layout
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or "~/.cache").expanduser() / "lotgdcli"


class _Session(requests.Session):
    """Keeps every request to an https server on https. Some servers (popetoad
    behind Cloudflare) redirect to http:// after login, which would send the
    session cookie in the clear."""

    def __init__(self, base):
        super().__init__()
        u = urlparse(base)
        self.https_host = u.hostname if u.scheme == "https" else None

    def secure(self, url):
        u = urlparse(url)
        if self.https_host and u.scheme == "http" and u.hostname == self.https_host:
            return u._replace(scheme="https").geturl()
        return url

    def get_redirect_target(self, resp):
        target = super().get_redirect_target(resp)
        return self.secure(urljoin(resp.url, target)) if target else target


class Client:
    def __init__(self, base_url=DEFAULT_URL, debug_dir=None):
        self.debug_dir = Path(debug_dir) if debug_dir else None
        self.n = 0
        if self.debug_dir:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
        self.base = base_url if base_url.endswith("/") else base_url + "/"
        self.s = _Session(self.base)
        self.s.headers["User-Agent"] = "lotgdcli/0.1 (terminal client)"
        self.s.cookies.set("template", SKIN, domain=urlparse(self.base).hostname, path="/")
        self.page = None
        self.logged_in = False
        # gear levels learned from the weapon/armor shop tables, kept per server
        # since the sidebar shows only names: {"weapon"|"armor": {name: level}}
        self.gear_file = CACHE_DIR / f"gear-{urlparse(self.base).hostname}.json"
        try:
            self.gear = json.loads(self.gear_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.gear = {}

    def learn_gear(self, page):
        changed = False
        for kind, items in page.gear.items():
            known = self.gear.setdefault(kind, {})
            if any(known.get(k) != v for k, v in items.items()):
                known.update(items)
                changed = True
        if changed:
            try:
                self.gear_file.parent.mkdir(parents=True, exist_ok=True)
                self.gear_file.write_text(json.dumps(self.gear, indent=1, sort_keys=True), encoding="utf-8")
            except OSError:
                pass  # coloring is a nicety; never break play over it

    def gear_level(self, kind, name):
        """(level, top) for an equipped item, or None if no shop table named it yet."""
        items = self.gear.get(kind, {})
        return (items[name], max(items.values())) if name in items else None

    def _load(self, resp):
        if self.debug_dir:
            self._dump(resp)
        resp.raise_for_status()
        self.page = parse(resp.text, resp.url)
        if self.page.gear:
            self.learn_gear(self.page)
        if self.debug_dir:
            self._log(f"    parsed: title={self.page.title!r} navs={len(self.page.navs)} "
                      f"forms={len(self.page.forms)} stats={len(self.page.stats)} body_chars={len(self.page.body.plain)}")
        return self.page

    def _log(self, line):
        with open(self.debug_dir / "requests.log", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _dump(self, resp):
        self.n += 1
        name = f"{self.n:03d}-{Path(urlparse(resp.url).path).stem or 'root'}.html"
        (self.debug_dir / name).write_text(resp.text, encoding="utf-8")
        hops = " -> ".join(f"{r.status_code} {r.url}" for r in resp.history)
        req = resp.request
        first = resp.history[0].request if resp.history else req
        self._log(f"{time.strftime('%H:%M:%S')} #{self.n} {first.method} {first.url}"
                  + (f"\n    redirects: {hops}" if hops else "")
                  + f"\n    final: {resp.status_code} {resp.url} ({len(resp.text)} bytes) -> {name}")

    def url(self, href):
        return self.s.secure(urljoin(self.page.url if self.page else self.base, href))

    def home(self):
        return self._load(self.s.get(self.base + "home.php", timeout=30))

    def mail(self):
        """Open the mail popup. mail.php doesn't touch the game's allowed navs,
        so the game page's links still work once you go back to it."""
        return self._load(self.s.get(self.base + "mail.php", timeout=30))

    def get(self, href):
        return self._load(self.s.get(self.url(href), timeout=30))

    def submit(self, form, values, button=None):
        data = dict(values)  # a value may be a list: same-name checkboxes (mail's msg[])
        if button and button[0]:
            data[button[0]] = button[1]
        target = self.url(form.action or (self.page.url if self.page else self.base))
        if form.method == "post":
            return self._load(self.s.post(target, data=data, timeout=30))
        return self._load(self.s.get(target, params=data, timeout=30))

    def login(self, name, password, progress=None):
        """Log in. progress(msg), if given, is called before each step and on each
        redirect the server answers with, so a UI can show where a slow login is."""
        say = progress or (lambda msg: None)
        host = urlparse(self.base).hostname
        if not self.page:
            say(f"Connecting to {host}...")
            self.home()

        def hop(resp, *args, **kwargs):
            if resp.is_redirect:
                nxt = Path(urlparse(resp.headers.get("location", "")).path).name or "home page"
                say(f"Server answered {resp.status_code}, loading {nxt}...")
            else:
                say("Reading the page...")

        say(f"Sending login for {name}...")
        page = self._load(self.s.post(self.base + "login.php", hooks={"response": hop},
                                      data={"name": name, "password": password}, timeout=30))
        self.logged_in = not self.is_logged_out(page)
        return page

    @staticmethod
    def is_logged_out(page):
        path = urlparse(page.url).path.rsplit("/", 1)[-1]
        return path in ("", "home.php", "index.php")
