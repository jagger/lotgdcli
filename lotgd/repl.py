"""Interactive loop: show a page, read a key, follow a nav or fill a form."""

import getpass
import os
import re
import sys
import termios
import tempfile
import tty
from itertools import zip_longest
from urllib.parse import urlparse

from rich.console import Console
from rich.table import Table
from rich.text import Text

HELP = """\
  <key>      follow the nav with that hotkey (no Enter needed)
  #<n>       follow nav or in-text link number n (e.g. shop items)
  :f[<n>]    fill and submit form n (default 1)
  :r         reload the current page
  :motd      show the message of the day
  :raw       save the current page's HTML to a temp file
  :login     log in again (e.g. after a timeout)
  :q         quit
  ?          this help"""


class Repl:
    def __init__(self, client, user=None, password=None):
        self.c = client
        self.user = user
        self.password = password
        self.con = Console(highlight=False)
        self.prev = None  # the page before the current one, for "that key was on the last page" hints

    # ---- rendering -------------------------------------------------------
    def show(self, page):
        con = self.con
        con.rule(page.title or "LoTGD", style="green")
        con.print(page.body)
        con.print()
        self.show_navs(page)
        self.show_stats(page)

    def show_stats(self, page):
        pairs = [(l, v) for l, v in page.stats if v]
        if not pairs:
            return
        hp = None
        for i, (label, value) in enumerate(pairs):
            if re.match(r"(hit ?points|hp|health)\b", label, re.I):
                hp = pairs.pop(i)
                break
        parts = []
        if hp:
            m = re.search(r"(-?\d+)\s*/\s*(\d+)", hp[1])
            cur, top = (int(m[1]), int(m[2])) if m else (None, None)
            ratio = cur / top if m and top else 1
            color = "bright_green" if ratio > 0.6 else "bright_yellow" if ratio > 0.3 else "bold bright_red"
            parts.append(Text.assemble(("HP ", "bold"), (f"{cur}/{top}" if m else hp[1], color)))
        xp = next(((l, v) for l, v in pairs if re.match(r"(experience|exp)\b", l, re.I)), None)
        if xp:
            pairs.remove(xp)
            num = re.match(r"[\d,]+(\s*/\s*[\d,]+)?", xp[1])
            bar = page.bars.get(xp[0])
            if bar:
                pct, color = bar
                ready = color == "blue" or pct >= 100
                parts.append(Text.assemble(("XP ", "bold"), (num[0] + " " if num else "", "bright_white"),
                                           (f"{pct}%", "bold bright_blue" if ready else "bright_white"),
                                           (" ⚔ fight your master!" if ready else "", "bold bright_blue")))
            else:
                parts.append(Text.assemble(("XP ", "bold"), (xp[1], "bright_white")))
        for label, value in pairs:
            if len(value) > 40:  # buff lists etc. would swamp the bar
                value = value[:39] + "…"
            parts.append(Text.assemble((label + " ", "dim"), (value, "bright_white")))
        self.con.rule(style="green")
        self.con.print(Text(" · ").join(parts))

    def show_navs(self, page):
        lines = []  # (Text, is_header)
        section = None
        for i, nav in enumerate(page.navs, 1):
            if nav.inline:  # already numbered in the page text
                continue
            if nav.section != section:
                section = nav.section
                if section:
                    lines.append((Text(f"— {section} —", style="bold yellow"), True))
            key = f"[{nav.key.upper()}]" if nav.key else f"[#{i}]"
            lines.append((Text.assemble((key.ljust(6), "bright_cyan"), nav.label), False))

        if lines:
            gap = 3
            colw = min(max(t.cell_len for t, _ in lines), 36)
            ncols = max(1, (self.con.width + gap) // (colw + gap))
            columns = self.flow(lines, ncols)
            grid = Table.grid(padding=(0, gap))
            for _ in columns:
                grid.add_column(width=colw, no_wrap=True, overflow="ellipsis")
            for row in zip_longest(*columns, fillvalue=Text("")):
                grid.add_row(*row)
            self.con.print(grid)
        if page.forms:
            typable = next((i for i, f in enumerate(page.forms, 1)
                            if any(fl.kind in ("text", "textarea") for fl in f.fields)), None)
            hint = f"  form {typable}: just start typing to fill it in" if typable else "  "
            others = [str(i) for i in range(1, len(page.forms) + 1) if i != typable]
            if others:
                hint += ("  ·  " if typable else "") + "buttons: " + ", ".join(f":f{i}" for i in others)
            self.con.print(Text(hint, style="dim cyan"))

    @staticmethod
    def flow(lines, ncols):
        """Split lines column-major into at most ncols columns of roughly
        equal height, never leaving a section header at a column's bottom."""
        height = -(-len(lines) // ncols)
        while True:
            cols, cur = [], []
            for text, header in lines:
                # start a new column when full, or when a header would be orphaned
                if cur and (len(cur) >= height or (header and len(cur) >= height - 1)):
                    cols.append(cur)
                    cur = []
                cur.append(text)
            cols.append(cur)
            if len(cols) <= ncols:
                return cols
            height += 1

    # ---- actions ---------------------------------------------------------
    def follow(self, cmd):
        page = self.c.page
        if cmd.startswith("#") and cmd[1:].isdigit():
            n = int(cmd[1:])
            if 1 <= n <= len(page.navs):
                return self.c.get(page.navs[n - 1].href)
            self.con.print("[red]no such nav[/]")
            return None
        if len(cmd) == 1:
            for nav in page.navs:
                if nav.key and nav.key.lower() == cmd.lower():
                    return self.c.get(nav.href)
        # fall back to a unique label prefix match (menu navs only: a stray key
        # shouldn't buy the shop item whose name happens to start with it)
        hits = [n for n in page.navs if not n.inline and n.label.lower().startswith(cmd.lower())]
        if len(hits) == 1:
            return self.c.get(hits[0].href)
        typable = next((i for i, f in enumerate(page.forms, 1)
                        if any(fl.kind in ("text", "textarea") for fl in f.fields)), None)
        if len(cmd) == 1 and cmd.isprintable() and not cmd.isspace() and typable:
            # not a hotkey: treat it as the start of typing into the page's text box
            return self.fill(typable, first=cmd)
        self.unknown_key(cmd)
        return None

    def unknown_key(self, cmd):
        was = None
        if self.prev and len(cmd) == 1:
            was = next((n for n in self.prev.navs if n.key and n.key.lower() == cmd.lower()), None)
        if was:
            self.con.print(f"[yellow]There's no \\[{cmd.upper()}] here any more. \\[{cmd.upper()}] {was.label} was on "
                           f"the previous page; this page has moved on (e.g. the fight is over).[/]")
        else:
            self.con.print(f"[yellow]No \\[{cmd.upper() if len(cmd) == 1 else cmd}] on this page. ? for help.[/]")

    def fill(self, n, first=None):
        forms = self.c.page.forms
        if not 1 <= n <= len(forms):
            self.con.print("[red]no such form[/]")
            return None
        form = forms[n - 1]
        try:
            return self._fill(form, first)
        except (KeyboardInterrupt, EOFError):
            self.con.print("\n[yellow]cancelled, nothing was sent[/]")
            return None

    def _fill(self, form, first):
        values = {}
        if not any(f.kind != "hidden" for f in form.fields):
            # a bare button (e.g. "give alms"): pressing it can cost gold, so ask
            label = form.buttons[0][1] if form.buttons else "Submit"
            if self.con.input(f"Press the [bold]{label}[/] button? \\[y/N]: ").strip().lower() != "y":
                self.con.print("[yellow]cancelled, nothing was sent[/]")
                return None
        for f in form.fields:
            if f.kind == "hidden":
                values[f.name] = f.value
                continue
            prompt = f.label or f.name
            if f.kind in ("select", "radio"):
                for i, (val, lab) in enumerate(f.options, 1):
                    mark = "*" if val == f.value else " "
                    self.con.print(f"   {mark}{i}. {lab}")
                ans = self.con.input(f"{prompt} [number, enter keeps *]: ").strip()
                values[f.name] = f.options[int(ans) - 1][0] if ans.isdigit() and 0 < int(ans) <= len(f.options) else f.value
            elif f.kind == "checkbox":
                ans = self.con.input(f"{prompt} [y/n, default {'y' if f.value else 'n'}]: ").strip().lower()
                on = (ans == "y") if ans else bool(f.value)
                if on:
                    values[f.name] = f.options[0][0]
            elif f.kind == "password":
                values[f.name] = getpass.getpass(f"{prompt}: ")
            else:
                ans = prefilled_input(f"{prompt}" + (f" [{f.value}]" if f.value else "") + ": ", first or "")
                first = None
                values[f.name] = ans if ans else f.value
        button = form.buttons[0]
        if len(form.buttons) > 1:
            for i, (_, lab) in enumerate(form.buttons, 1):
                self.con.print(f"   {i}. {lab}")
            ans = self.con.input("button [1]: ").strip()
            if ans.isdigit() and 0 < int(ans) <= len(form.buttons):
                button = form.buttons[int(ans) - 1]
        return self.c.submit(form, values, button)

    def login(self):
        if not self.user:
            self.user = self.con.input("Character name: ").strip()
        if not self.password:
            self.password = getpass.getpass("Password: ")
        page = self.c.login(self.user, self.password)
        if not self.c.logged_in:
            self.password = None
            self.con.print("[bold red]Login failed.[/]")
        return page

    # ---- input -----------------------------------------------------------
    def read_command(self):
        """One keypress picks a nav; ':', '#' or '?' starts a typed command."""
        if not sys.stdin.isatty():
            return self.con.input("[bold green]> [/]").strip()
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
        self.con.print("[bold green]> [/]", end="")
        key = getch()
        if key in ("\x03", "\x04"):  # ctrl-c / ctrl-d
            raise KeyboardInterrupt
        if key in (":", "#"):
            return (key + self.con.input(key)).strip()
        if key in ("\r", "\n", " "):
            self.con.print()
            return ""
        self.con.print(key)
        return key

    # ---- main loop -------------------------------------------------------
    def run(self):
        page = self.login() if self.user is not None or self.password else self.c.home()
        while True:
            self.show(page)
            if self.c.logged_in and self.c.is_logged_out(page):
                self.c.logged_in = False
                self.con.print("[yellow]You've been logged out (session expired?). Type :login to log back in.[/]")
            try:
                cmd = self.read_command()
            except (EOFError, KeyboardInterrupt):
                self.con.print()
                return
            if not cmd:
                continue
            new = None
            try:
                if cmd in (":q", ":quit"):
                    return
                elif cmd == "?":
                    self.con.print(HELP)
                elif cmd == ":r":
                    new = self.c.get(page.url)
                elif cmd == ":motd":
                    motd = self.c.s.get(self.c.base + "motd.php", timeout=30)
                    from .parser import parse
                    self.con.print(parse(motd.text).body)
                elif cmd == ":raw":
                    fd, path = tempfile.mkstemp(prefix="lotgd-", suffix=".html")
                    with os.fdopen(fd, "w") as fh:
                        fh.write(page.html)
                    self.con.print(f"saved {path}")
                elif cmd == ":login":
                    new = self.login()
                elif cmd == ":f" or (cmd.startswith(":f") and cmd[2:].isdigit()):
                    new = self.fill(int(cmd[2:]) if len(cmd) > 2 else 1)
                else:
                    new = self.follow(cmd)
            except Exception as e:  # network hiccups shouldn't kill the session
                self.con.print(f"[red]error: {e}[/]")
            if new is not None:
                if urlparse(new.url).path.endswith("badnav.php") and cmd != ":login":
                    self.con.print("[bold yellow]The server didn't accept that action (it re-showed an earlier "
                                   "page). Nothing new happened: no gold spent, no turn used.[/]")
                    self.con.input("[dim](enter to continue)[/]")
                self.prev, page = page, new
            elif cmd not in ("?", ":raw", ":motd"):
                continue
            else:
                self.con.input("[dim](enter to continue)[/]")


def getch():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def prefilled_input(prompt, text=""):
    """input() with `text` already typed in (and editable), via readline."""
    if not text:
        return input(prompt)
    try:
        import readline
    except ImportError:
        return text + input(prompt + text)
    readline.set_startup_hook(lambda: readline.insert_text(text))
    try:
        return input(prompt)
    finally:
        readline.set_startup_hook()
