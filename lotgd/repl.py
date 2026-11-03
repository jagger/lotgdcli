"""Interactive loop: show a page, read a key, follow a nav or fill a form."""

import getpass
import os
import sys
import termios
import time
import tempfile
import tty
from itertools import zip_longest
from urllib.parse import urlparse

import requests
from rich import box
from rich.console import Console, Group
from rich.markup import escape
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .sidebar import header, stat_lines, stat_summary
from .paths import RAW_DIR

HELP = """\
  <key>      follow the nav with that hotkey (no Enter needed)
  #<n>       follow nav or in-text link number n (e.g. shop items)
  :f[<n>]    fill and submit form n (default 1)
  :mail      open your mail (Ye Olde Mail); :back returns to the game
  PgDn PgUp  scroll long page text (space, arrow keys too)
  :r         reload the current page
  :motd      show the message of the day
  :raw       save the current page's HTML under ~/.lotgdcli/cache/raw
  :login     log in again (e.g. after a timeout)
  :q         quit
  ?          this help"""

PANE_MIN_WIDTH = 100  # narrower terminals keep the stacked layout
NAV_WIDTH = 28  # menu pane
NAV_WIDTH_2COL = 22  # each menu column when a long menu flows into two
STAT_WIDTH = 30  # stats pane
MAIL_HINT = "✉ mail · #n follows a link · :back returns to the game"


class Repl:
    def __init__(self, client, user=None, password=None, login=None):
        self.c = client
        self.user = user
        self.password = password
        self.want_login = (user is not None or bool(password)) if login is None else login
        self.con = Console(highlight=False)
        self.prev = None  # the page before the current one, for "that key was on the last page" hints
        self.notes = []  # messages to print under the next page, since show() clears the screen
        self.game = None  # the game page to go back to while the mail popup is open
        self.shown = None  # the page on screen, and how far its text is scrolled
        self.scroll = 0
        self.page_rows = 0  # rows of page text the last frame showed
        self.more = ""  # scroll position hint for the command bar

    # ---- rendering -------------------------------------------------------
    def note(self, markup):
        """A message for the command bar. The screen is redrawn to show it, so it
        never prints below the prompt and scrolls the top of the screen away."""
        self.notes.append(markup)

    def show(self, page):
        con = self.con
        if page is not self.shown:
            self.scroll = 0  # a new page starts at its top
            self.shown = page
        con.clear()  # each page starts at the top, so the menu doesn't jump around (no-op when piped)
        if con.is_terminal and con.width >= PANE_MIN_WIDTH:
            self.show_panes(page)
            self.notes = []
            return
        con.rule(Text(page.title or "LoTGD", style="bold"), style="green")
        con.print(page.body)
        con.print()
        self.show_navs(page)
        stats = stat_summary(page, self.c.gear_level)
        if stats:
            con.rule(style="green")
            for line in stats:
                con.print(line)
        if self.game is not None:
            con.rule(style="green")
            con.print(Text(MAIL_HINT, style="dim cyan"))
        for note in self.notes:
            con.print(note)
        self.notes = []

    def bar_lines(self, page, width):
        """The command bar: form/mail hints and messages, with help on the right."""
        left = [Text(h.strip(), style="dim cyan") for h in (self.form_hint(page),
                MAIL_HINT if self.game is not None else "") if h.strip()]
        left += [n if isinstance(n, Text) else Text.from_markup(str(n)) for n in self.notes]
        right = Text("? help · :q quit", style="dim")
        if self.more:
            right = Text.assemble((self.more + " · ", "bright_cyan"), right)
        first = left[0] if left else Text()
        if first.cell_len + right.cell_len + 2 <= width:
            return [Text.assemble(first, " " * (width - first.cell_len - right.cell_len), right)] + left[1:]
        return left + [Text.assemble(" " * max(0, width - right.cell_len), right)]

    def show_panes(self, page):
        """Menu on the left, page text in the middle, stats on the right, and a
        command bar at the bottom. The frame is exactly one screen tall, so the
        prompt lands on the last row and nothing scrolls off the top: long page
        text scrolls inside its pane instead (PgUp/PgDn, space)."""
        con = self.con
        width, height = con.width, con.height
        stats = stat_lines(page, self.c.gear_level, STAT_WIDTH)
        self.more = ""
        bar = self.bar_lines(page, width - 4)
        avail = max(3, height - 1 - 2 - 1 - len(bar))  # prompt, top/bottom border, rule
        navs, navw = self.nav_column(page, avail)
        # panel border 2, each column padded 1+1, a separator between columns
        ncols = 1 + bool(navs) + bool(stats)
        bodyw = (width - 2 - (navw + 2 if navs else 0) - (STAT_WIDTH + 2 if stats else 0)
                 - (ncols - 1) - 2)

        body = list(page.body.wrap(con, bodyw, overflow="fold"))
        last = max(0, len(body) - avail)
        self.scroll = max(0, min(self.scroll, last))
        self.page_rows = avail
        shown = body[self.scroll:self.scroll + avail]
        if last:
            arrows = ("▲" if self.scroll else " ") + ("▼" if self.scroll < last else " ")
            self.more = f"{arrows} lines {self.scroll + 1}–{self.scroll + len(shown)} of {len(body)}, PgUp/PgDn"
            bar = self.bar_lines(page, width - 4)  # now with the scroll hint
        shown += [Text("")] * (avail - len(shown))

        grid = Table(box=box.SQUARE, show_header=False, show_edge=False, expand=True,
                     padding=(0, 1), border_style="green")
        cells = []
        if navs:  # popups (mail) have no menu: give the text the room
            grid.add_column(width=navw, no_wrap=True, overflow="ellipsis")
            cells.append(Text("\n").join(navs[:avail]))
        grid.add_column(width=bodyw, no_wrap=True, overflow="crop")
        cells.append(Text("\n").join(shown))
        if stats:  # logged out there are none: give the text the room
            grid.add_column(width=STAT_WIDTH, no_wrap=True, overflow="ellipsis")
            if len(stats) > avail:
                stats = stats[:avail - 1] + [Text("…", style="dim")]
            cells.append(Text("\n").join(stats))
        grid.add_row(*cells)
        title = Text(" " + (page.title or "LoTGD") + " ", style="bold bright_white")
        con.print(Panel(Group(grid, Rule(style="green"), Padding(Group(*bar), (0, 1))),
                        title=title, title_align="left", border_style="green", padding=0,
                        box=box.ROUNDED, height=height - 1))

    def nav_column(self, page, avail):
        """The menu as lines for the left pane. A menu taller than the pane flows
        into two columns. Returns (lines, width)."""
        lines = self.nav_lines(page)
        if not lines:
            return [], 8
        colw = min(max(t.cell_len for t, _ in lines), NAV_WIDTH)
        if len(lines) <= avail:
            return [fit(t, colw) for t, _ in lines], colw
        colw = min(colw, NAV_WIDTH_2COL)
        left, *rest = self.flow(lines, 2)
        right = rest[0] if rest else []
        out = []
        for a, b in zip_longest(left, right, fillvalue=Text("")):
            a = fit(a, colw)
            out.append(Text.assemble(a, " " * (colw - a.cell_len + 2), fit(b, colw)))
        return out, colw * 2 + 2

    def nav_lines(self, page):
        """Menu entries as [(Text, is_header)], with section headers; in-text links are skipped."""
        lines = []
        section = None
        for i, nav in enumerate(page.navs, 1):
            if nav.inline:  # already numbered in the page text
                continue
            if nav.section != section:
                section = nav.section
                if section:
                    lines.append((header(section, NAV_WIDTH), True))
            key = f"[{nav.key.upper()}]" if nav.key else f"[#{i}]"
            lines.append((Text.assemble((key.ljust(6), "bright_cyan"), nav.label), False))
        return lines

    @staticmethod
    def form_hint(page):
        if not page.forms:
            return ""
        typable = next((i for i, f in enumerate(page.forms, 1)
                        if any(fl.kind in ("text", "textarea") for fl in f.fields)), None)
        hint = f"  form {typable}: just start typing to fill it in" if typable else "  "
        others = [str(i) for i in range(1, len(page.forms) + 1) if i != typable]
        if others:
            hint += ("  ·  " if typable else "") + "buttons: " + ", ".join(f":f{i}" for i in others)
        return hint

    def show_navs(self, page):
        lines = self.nav_lines(page)
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
            self.con.print(Text(self.form_hint(page), style="dim cyan"))

    @staticmethod
    def flow(lines, ncols):
        """Split lines column-major into at most ncols columns of roughly
        equal height, never leaving a section header at a column's bottom."""
        height = -(-len(lines) // ncols)
        while True:
            cols, cur = [], []
            for text, is_header in lines:
                # start a new column when full, or when a header would be orphaned
                if cur and (len(cur) >= height or (is_header and len(cur) >= height - 1)):
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
            self.note(f"[yellow]No #{n} on this page.[/]")
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
            self.note(f"[yellow]No \\[{cmd.upper()}] here any more: \\[{cmd.upper()}] {escape(was.label)} was on "
                      f"the previous page (e.g. the fight is over).[/]")
        else:
            self.note(f"[yellow]No \\[{escape(cmd.upper() if len(cmd) == 1 else cmd)}] on this page. ? for help.[/]")

    def fill(self, n, first=None):
        forms = self.c.page.forms
        if not 1 <= n <= len(forms):
            self.note(f"[yellow]No form {n} on this page.[/]")
            return None
        form = forms[n - 1]
        try:
            return self._fill(form, first)
        except (KeyboardInterrupt, EOFError):
            self.con.print()
            self.note("[yellow]Cancelled, nothing was sent.[/]")
            return None

    def _fill(self, form, first):
        values = {}
        if self.con.is_terminal:
            # the field prompts take over the "> " line the key or :f was typed on
            self.con.file.write("\x1b[1A\r\x1b[2K")
        if not any(f.kind != "hidden" for f in form.fields):
            # a bare button (e.g. "give alms"): pressing it can cost gold, so ask
            label = form.buttons[0][2]
            if self.con.input(f"[bold green]Press \\[{escape(label)}]?[/] \\[y/N] ").strip().lower() != "y":
                self.note("[yellow]Cancelled, nothing was sent.[/]")
                return None
        for f in form.fields:
            if f.kind == "hidden":
                values[f.name] = f.value
                continue
            prompt = (f.label or f.name).rstrip(" :")
            if f.kind in ("select", "radio"):
                for i, (val, lab) in enumerate(f.options, 1):
                    mark = "*" if val == f.value else " "
                    self.con.print(f"   {mark}{i}. {lab}")
                ans = self.con.input(f"[bold green]{escape(prompt)}[/] [dim](number, enter keeps *)[/] ").strip()
                values[f.name] = f.options[int(ans) - 1][0] if ans.isdigit() and 0 < int(ans) <= len(f.options) else f.value
            elif f.kind == "checkbox":
                ans = self.con.input(f"[bold green]{escape(prompt)}[/] [dim](y/n, enter keeps {'y' if f.value else 'n'})[/] ").strip().lower()
                on = (ans == "y") if ans else bool(f.value)
                if on:
                    v = f.options[0][0]
                    if f.name.endswith("[]"):  # one box per row, all named msg[] (mail inbox)
                        values.setdefault(f.name, []).append(v)
                    else:
                        values[f.name] = v
            elif f.kind == "textarea":
                # one line of input; `n is LoTGD's line break. A prefilled textarea
                # (a reply's quoted original) keeps its text under what you type.
                quoted = f.value.strip()
                hint = " (`n = new line" + (", the quoted message stays below)" if quoted else ")")
                self.con.print(Text(hint, style="dim"))
                ans = prefilled_input(field_prompt(prompt), first or "")
                first = None
                values[f.name] = ans.replace("`n", "\n") + f.value if ans else f.value
            elif f.kind == "password":
                values[f.name] = getpass.getpass(field_prompt(prompt).replace("\001", "").replace("\002", ""))
            else:
                ans = prefilled_input(field_prompt(prompt, f.value), first or "")
                first = None
                values[f.name] = ans if ans else f.value
        button = form.buttons[0]
        if len(form.buttons) > 1:
            for i, (_, _, lab) in enumerate(form.buttons, 1):
                self.con.print(f"   {i}. {escape(lab)}")
            ans = self.con.input(f"[bold green]Press which button?[/] [dim](enter = {escape(button[2])})[/] ").strip()
            if ans.isdigit() and 0 < int(ans) <= len(form.buttons):
                button = form.buttons[int(ans) - 1]
        return self.c.submit(form, values, button)

    def login(self):
        if not self.user:
            self.user = self.con.input("Character name: ").strip()
        if not self.password:
            self.password = getpass.getpass("Password: ")
        start = time.monotonic()
        with self.con.status("Logging in...") as status:
            page = self.c.login(self.user, self.password,
                                progress=lambda msg: status.update(escape(msg)))
        took = time.monotonic() - start
        if not self.c.logged_in:
            self.password = None
            self.notes.append(f"[bold red]Login failed[/] [dim]({took:.1f}s). Check the name and password.[/]")
        else:
            self.notes.append(f"[dim]Logged in as {escape(self.user)} ({took:.1f}s).[/]")
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
        if key.startswith("\x1b"):  # PgUp/PgDn/arrows arrive as escape sequences
            return SCROLL_KEYS.get(key[1:], "")
        if key == " " and self.more:
            return ":down"
        if key in (":", "#"):
            return (key + self.con.input(key)).strip()
        if key in ("\r", "\n", " "):
            self.con.print()
            return ""
        self.con.print(key)
        return key

    # ---- main loop -------------------------------------------------------
    def run(self):
        try:
            page = self.login() if self.want_login else self.c.home()
        except (EOFError, KeyboardInterrupt):
            self.con.print()
            return 1
        except requests.RequestException as e:
            self.con.print(f"[bold red]Couldn't connect to {escape(self.c.base)}:[/] {escape(str(e))}")
            return 1
        while True:
            if self.c.logged_in and self.c.is_logged_out(page):
                self.c.logged_in = False
                self.note("[yellow]You've been logged out (session expired?). Type :login to log back in.[/]")
            self.show(page)
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
                elif cmd in SCROLL_KEYS.values():
                    rows = max(1, self.page_rows - 2) if cmd in (":down", ":up") else 1
                    self.scroll += rows if cmd.endswith("down") else -rows
                    continue
                elif cmd == "?":
                    self.con.print(HELP)
                elif cmd == ":r":
                    new = self.c.get(page.url)
                elif cmd == ":motd":
                    motd = self.c.s.get(self.c.base + "motd.php", timeout=30)
                    from .parser import parse
                    self.con.print(parse(motd.text).body)
                elif cmd == ":raw":
                    RAW_DIR.mkdir(parents=True, exist_ok=True)
                    fd, path = tempfile.mkstemp(prefix="lotgd-", suffix=".html", dir=RAW_DIR)
                    with os.fdopen(fd, "w", encoding="utf-8") as fh:
                        fh.write(page.html)
                    self.note(f"Saved {escape(path)}")
                elif cmd == ":login":
                    self.game = None
                    new = self.login()
                elif cmd in (":mail", ":m") and self.game is None:
                    if not self.c.logged_in:
                        self.note("[yellow]Log in first (:login) to read your mail.[/]")
                    else:
                        new = self.c.mail()
                        self.game = page
                elif cmd in (":back", ":b", ":mail", ":m") and self.game is not None:
                    # back to the game page as it was: no request, and its links still work
                    new, self.game = self.game, None
                    self.c.page = new
                elif cmd == ":f" or (cmd.startswith(":f") and cmd[2:].strip().isdigit()):
                    new = self.fill(int(cmd[2:]) if cmd[2:].strip() else 1)  # ":f2" or ":f 2"
                else:
                    new = self.follow(cmd)
            except Exception as e:  # network hiccups shouldn't kill the session
                self.note(f"[red]Error: {escape(str(e))}[/]")
            if new is not None:
                if self.game is not None and self.c.is_logged_out(new):
                    self.game = None  # mail redirected to the login page: the session timed out
                if urlparse(new.url).path.endswith("badnav.php") and cmd != ":login":
                    self.con.print("[bold yellow]The server didn't accept that action (it re-showed an earlier "
                                   "page). Nothing new happened: no gold spent, no turn used.[/]")
                    self.con.input("[dim](enter to continue)[/]")
                self.prev, page = page, new
            elif cmd in ("?", ":motd"):
                self.con.input("[dim](enter to continue)[/]")
            # anything else that changed nothing (unknown key, error, cancelled) left a
            # note: the redraw shows it in the command bar, in place


SCROLL_KEYS = {"[6~": ":down", "[5~": ":up", "[B": ":line-down", "[A": ":line-up",
               "OB": ":line-down", "OA": ":line-up"}


def getch():
    """One keypress in raw mode: a character, or a whole escape sequence such as
    "\\x1b[6~" (PgDn). Reads the fd directly so no bytes hide in Python's buffer."""
    import select
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        b = os.read(fd, 1)
        if b == b"\x1b":
            while len(b) < 8 and select.select([fd], [], [], 0.05)[0]:
                b += os.read(fd, 1)
                if b[-1:].isalpha() or b.endswith(b"~"):
                    break
        elif b and b[0] >= 0xC0:  # rest of a UTF-8 character
            need = 1 if b[0] < 0xE0 else 2 if b[0] < 0xF0 else 3
            b += os.read(fd, need)
        return b.decode(errors="replace")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def field_prompt(label, default=""):
    """A readline-safe input() prompt styled like the "> " command prompt.
    \001/\002 tell readline the colour codes take no width, so editing keeps its place."""
    if len(default) > 30:
        default = default[:29] + "…"
    hint = f" \001\x1b[2m\002[{default}]\001\x1b[0m\002" if default else ""
    return f"\001\x1b[1;32m\002{label}\001\x1b[0m\002{hint} > "


def prefilled_input(prompt, text=""):
    """input() with `text` already typed in (and editable), via readline."""
    try:
        import readline
    except ImportError:
        prompt = prompt.replace("\001", "").replace("\002", "")
        return text + input(prompt + text)
    if not text:
        return input(prompt)
    readline.set_startup_hook(lambda: readline.insert_text(text))
    try:
        return input(prompt)
    finally:
        readline.set_startup_hook()


def fit(t, w):
    """t cut to w cells with an ellipsis, if it's wider."""
    if t.cell_len <= w:
        return t
    t = t.copy()
    t.truncate(w, overflow="ellipsis")
    return t
