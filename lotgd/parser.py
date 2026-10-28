"""Turn a LoTGD page (jade skin) into a Page: body text, navs, forms, stats."""

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from rich.style import Style
from rich.text import Text

from .colors import style_for

BLOCK_TAGS = {"p", "div", "table", "tr", "center", "h1", "h2", "h3", "h4", "ul", "ol", "li", "hr", "blockquote"}
SKIP_TAGS = {"script", "style", "noscript", "head", "title", "select", "textarea", "option"}
BUTTON_TYPES = {"submit", "image", "button", "reset"}


@dataclass
class Nav:
    section: str
    key: str  # hotkey letter, may be ""
    label: str
    href: str


@dataclass
class Field:
    name: str
    kind: str  # text, password, hidden, select, textarea, checkbox, radio
    value: str = ""
    options: list = field(default_factory=list)  # [(value, label)] for select/radio
    label: str = ""


@dataclass
class Form:
    action: str
    method: str
    fields: list
    buttons: list  # [(name, value)]


@dataclass
class Page:
    url: str
    title: str
    body: Text
    navs: list
    forms: list
    stats: list  # [(label, value)]; value "" marks a section header
    html: str
    bars: dict = field(default_factory=dict)  # label -> (percent, color) from stat bars


def _clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _ws(s):
    """Collapse whitespace the way a browser does, but keep a single space."""
    return re.sub(r"\s+", " ", s)


class _Renderer:
    def __init__(self):
        self.text = Text()
        self.form_no = 0

    def newline(self):
        if self.text.plain and not self.text.plain.endswith("\n"):
            self.text.append("\n")

    def render(self, node, style=None):
        for child in node.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                s = _ws(str(child))
                if self.text.plain.endswith(("\n", " ")) or not self.text.plain:
                    s = s.lstrip()
                if s:
                    self.text.append(s, style=style)
                continue
            if not isinstance(child, Tag) or child.name in SKIP_TAGS:
                continue
            self.tag(child, style)

    def bar(self, el, style):
        """FightBar: an outer div of fixed px width holding a colored inner div."""
        inner = el.find("div", recursive=False)
        ow = re.search(r"width:\s*(\d+)px", el.get("style", ""))
        iw = re.search(r"width:\s*(\d+)px", inner.get("style", "")) if inner else None
        if not (ow and iw) or int(ow[1]) == 0:
            return False
        filled = round(10 * min(int(iw[1]), int(ow[1])) / int(ow[1]))
        color = re.search(r"background-color:\s*([^;]+)", inner.get("style", ""))
        try:
            fill_style = Style.parse(color[1].strip()) if color else None
        except Exception:
            fill_style = None
        self.text.append("█" * filled, style=fill_style or "bright_green")
        self.text.append("░" * (10 - filled) + " ", style="dim")
        return True

    def tag(self, el, style):
        name = el.name
        st = style_for(el.get("class")) or style
        if name == "font" and el.get("color"):
            st = el["color"] if re.fullmatch(r"#[0-9a-fA-F]{6}", el["color"]) else st
        if name in ("b", "strong"):
            st = f"{st} bold" if st else "bold"
        elif name in ("i", "em"):
            st = f"{st} italic" if st else "italic"
        elif name == "u":
            st = f"{st} underline" if st else "underline"

        if name == "br":
            self.text.append("\n")
            return
        if name == "img":
            return
        if name == "div" and self.bar(el, st):
            return
        if name == "form":
            self.form_no += 1
            self.newline()
            self.text.append(f"[form {self.form_no}] ", style="dim cyan")
            self.render(el, st)
            self.newline()
            return
        if name == "input":
            kind = (el.get("type") or "text").lower()
            if kind in BUTTON_TYPES:
                self.text.append(f"<{el.get('value') or el.get('alt') or kind}> ", style="dim cyan")
            elif kind != "hidden":
                self.text.append(f"[{el.get('name', '?')}] ", style="dim cyan")
            return
        if name in ("select", "textarea"):
            self.text.append(f"[{el.get('name', '?')}] ", style="dim cyan")
            return
        if name in ("td", "th"):
            self.render(el, st)
            if not self.text.plain.endswith(("\n", " ")):
                self.text.append("  ")
            return

        block = name in BLOCK_TAGS
        if block:
            self.newline()
        if name == "hr":
            self.text.append("─" * 40 + "\n", style="dim")
            return
        if name == "li":
            self.text.append("• ")
        self.render(el, st)
        if block:
            self.newline()


def render_text(el):
    r = _Renderer()
    r.render(el)
    t = r.text
    # squeeze runs of blank lines
    plain = t.plain
    out = Text()
    blank = 0
    for line in t.split("\n", allow_blank=True):
        if line.plain.strip():
            blank = 0
            line.rstrip()
            out.append_text(line)
            out.append("\n")
        elif out.plain and blank == 0:
            blank = 1
            out.append("\n")
    out.rstrip()
    return out


def parse_navs(soup):
    navs = []
    for cell in soup.select("td.nav"):
        if not cell.select_one("a.nav"):
            continue
        section = ""
        for el in cell.find_all(["span", "a"]):
            classes = el.get("class") or []
            if el.name == "span" and "navhead" in classes:
                section = _clean(el.get_text()).strip("—- ")
            elif el.name == "a" and "nav" in classes and el.get("href"):
                key = el.get("accesskey") or ""
                if isinstance(key, list):  # bs4 treats accesskey as multi-valued
                    key = key[0] if key else ""
                if not key:
                    hi = el.select_one("span.navhi")
                    key = _clean(hi.get_text()) if hi else ""
                navs.append(Nav(section, key[:1], _clean(el.get_text()), el["href"]))
    return navs


def parse_forms(root):
    forms = []
    for f in root.find_all("form"):
        fields, buttons, radios = [], [], {}
        for el in f.find_all(["input", "select", "textarea"]):
            name = el.get("name")
            if el.name == "input":
                kind = (el.get("type") or "text").lower()
                if kind in BUTTON_TYPES:
                    if kind in ("submit", "image"):
                        buttons.append((name, el.get("value") or el.get("alt") or "Submit"))
                    continue
                if not name:
                    continue
                if kind == "radio":
                    fld = radios.get(name)
                    if not fld:
                        fld = radios[name] = Field(name, "radio")
                        fields.append(fld)
                    lbl = _clean(el.next_sibling) if isinstance(el.next_sibling, NavigableString) else ""
                    fld.options.append((el.get("value", "on"), lbl or el.get("value", "on")))
                    if el.has_attr("checked"):
                        fld.value = el.get("value", "on")
                elif kind == "checkbox":
                    fields.append(Field(name, "checkbox", el.get("value", "on") if el.has_attr("checked") else "",
                                        [(el.get("value", "on"), "on")]))
                else:
                    fields.append(Field(name, kind if kind in ("hidden", "password") else "text", el.get("value", "")))
            elif el.name == "select" and name:
                opts = [(o.get("value", _clean(o.get_text())), _clean(o.get_text())) for o in el.find_all("option")]
                sel = el.find("option", selected=True)
                val = sel.get("value", _clean(sel.get_text())) if sel else (opts[0][0] if opts else "")
                fields.append(Field(name, "select", val, opts))
            elif el.name == "textarea" and name:
                fields.append(Field(name, "textarea", el.get_text()))
        for fld in fields:
            lab = root.find("label", attrs={"for": fld.name})
            if lab:
                fld.label = _clean(lab.get_text())
        forms.append(Form(f.get("action") or "", (f.get("method") or "get").lower(), fields, buttons or [(None, "Submit")]))
    return forms


def parse_bar(cell):
    """Read a stat bar (expbar/healthbar modules): a nested table whose first
    td has width='<pct>%'. expbar colors it blue once you can face your master."""
    td = cell.select_one("table td[width]")
    m = re.fullmatch(r"\s*(\d+)%\s*", td.get("width", "")) if td else None
    return (int(m[1]), (td.get("bgcolor") or "").lower()) if m else None


def parse_stats(cell, bars=None):
    stats = []
    if not cell:
        return stats
    # jade's statstart/stathead/statrow templates: a table.charinfo whose rows are
    # either one td.charhead (section title) or two td.charinfo (label, value).
    # Values like Hitpoints can hold a nested health-bar table, so only walk the
    # charinfo table's own rows.
    for table in cell.find_all("table", class_="charinfo"):
        rows = table.find_all("tr", recursive=False) or [
            tr for tr in table.find_all("tr") if tr.find_parent("table") is table]
        pending = None  # statbuff: "Buffs:" header row followed by a colspan value row
        for tr in rows:
            tds = tr.find_all("td", recursive=False)
            if not tds:
                continue
            first = tds[0]
            if "charhead" in (first.get("class") or []):
                pending = _clean(first.get_text()).rstrip(":")
                stats.append((pending, ""))
            elif len(tds) == 1:
                txt = _clean(first.get_text(" "))
                if pending and txt and stats and stats[-1] == (pending, ""):
                    stats[-1] = (pending, txt)
                pending = None
            else:
                label, value = _clean(first.get_text()).rstrip(":"), _clean(tds[1].get_text(" "))
                if label:
                    stats.append((label, value))
                    bar = parse_bar(tds[1])
                    if bar and bars is not None:
                        bars[label] = bar
                pending = None
    if stats:
        return stats
    for tr in cell.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) >= 2:
            label, value = _clean(tds[0].get_text()).rstrip(":"), _clean(tds[1].get_text(" "))
            if label:
                stats.append((label, value))
    if not stats:
        txt = _clean(cell.get_text(" "))
        if txt:
            stats.append((txt, ""))
    return stats


def parse(html, url=""):
    # LoTGD keeps color <span>s open across raw table output (e.g. fight health
    # bars), so the HTML is misnested. html5lib recovers the way browsers do;
    # html.parser lets a stray </td> close the main content cell mid-fight.
    soup = BeautifulSoup(html, "html5lib")
    title = _clean(soup.title.get_text()) if soup.title else ""

    head = soup.select_one("td.headrow")
    main = head.find("td", attrs={"width": "100%"}) if head else None
    main = main or soup.body or soup
    for sel in main.find_all("select", attrs={"name": "template"}):
        sel.find_parent("form").decompose()  # skin picker; we pin our own skin

    side = head.find("td", attrs={"width": "120"}) if head else None
    side_cell = side.select_one("td.nav") if side else None
    if side_cell:
        for f in side_cell.find_all("form"):
            f.decompose()

    bars = {}
    stats = parse_stats(side_cell, bars)
    return Page(
        url=url,
        title=title,
        body=render_text(main),
        navs=parse_navs(soup),
        forms=parse_forms(main),
        stats=stats,
        html=html,
        bars=bars,
    )
