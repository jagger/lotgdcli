"""HTTP session against a LoTGD server."""

import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from .parser import parse

DEFAULT_URL = "https://lotgd.popetoad.com/"
SKIN = "legacy:jade.htm"  # parser is written against this skin's layout


class Client:
    def __init__(self, base_url=DEFAULT_URL, debug_dir=None):
        self.debug_dir = Path(debug_dir) if debug_dir else None
        self.n = 0
        if self.debug_dir:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
        self.base = base_url if base_url.endswith("/") else base_url + "/"
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "lotgdcli/0.1 (terminal client)"
        self.s.cookies.set("template", SKIN, domain=urlparse(self.base).hostname, path="/")
        self.page = None
        self.logged_in = False

    def _load(self, resp):
        if self.debug_dir:
            self._dump(resp)
        resp.raise_for_status()
        self.page = parse(resp.text, resp.url)
        if self.debug_dir:
            self._log(f"    parsed: title={self.page.title!r} navs={len(self.page.navs)} "
                      f"forms={len(self.page.forms)} stats={len(self.page.stats)} body_chars={len(self.page.body.plain)}")
        return self.page

    def _log(self, line):
        with open(self.debug_dir / "requests.log", "a") as fh:
            fh.write(line + "\n")

    def _dump(self, resp):
        self.n += 1
        name = f"{self.n:03d}-{Path(urlparse(resp.url).path).stem or 'root'}.html"
        (self.debug_dir / name).write_text(resp.text)
        hops = " -> ".join(f"{r.status_code} {r.url}" for r in resp.history)
        req = resp.request
        self._log(f"{time.strftime('%H:%M:%S')} #{self.n} {req.method} {req.url}"
                  + (f"\n    redirects: {hops}" if hops else "")
                  + f"\n    final: {resp.status_code} {resp.url} ({len(resp.text)} bytes) -> {name}")

    def url(self, href):
        return urljoin(self.page.url if self.page else self.base, href)

    def home(self):
        return self._load(self.s.get(self.base + "home.php", timeout=30))

    def get(self, href):
        return self._load(self.s.get(self.url(href), timeout=30))

    def submit(self, form, values, button=None):
        data = dict(values)
        if button and button[0]:
            data[button[0]] = button[1]
        target = self.url(form.action or (self.page.url if self.page else self.base))
        if form.method == "post":
            return self._load(self.s.post(target, data=data, timeout=30))
        return self._load(self.s.get(target, params=data, timeout=30))

    def login(self, name, password):
        if not self.page:
            self.home()
        page = self._load(self.s.post(self.base + "login.php",
                                      data={"name": name, "password": password}, timeout=30))
        self.logged_in = not self.is_logged_out(page)
        return page

    @staticmethod
    def is_logged_out(page):
        path = urlparse(page.url).path.rsplit("/", 1)[-1]
        return path in ("", "home.php", "index.php")
