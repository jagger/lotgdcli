"""Stats for the sidebar: grouped under the server's own categories (Character
Info, Personal Info, Currency, Equipment Info, ...), with HP/XP bars, rarity-colored
gear, and short stats packed into columns so the sidebar stays short."""

import re

from rich.text import Text

from .colors import gear_style

# shorter labels so short stats pack two or three to a row
SHORT = {
    "strength": "Str", "dexterity": "Dex", "intelligence": "Int", "constitution": "Con",
    "wisdom": "Wis", "attack": "Atk", "defense": "Def", "speed": "Spd", "bankgold": "Bank",
    "charm": "Charm", "favor": "Favor",
}
HEADER_STYLE = "bold yellow"
RULE_STYLE = "green"
BAR_WIDTH = 10


def header(name, width):
    """── Name ─────── in the same style as the menu's section headers."""
    name = name if len(name) <= width - 4 else name[: width - 5] + "…"
    return Text.assemble(("── ", RULE_STYLE), (name, HEADER_STYLE),
                         (" " + "─" * max(0, width - len(name) - 4), RULE_STYLE))


def bar(ratio, style):
    filled = max(0, min(BAR_WIDTH, round(ratio * BAR_WIDTH)))
    return Text.assemble(("█" * filled, style), ("░" * (BAR_WIDTH - filled), "grey35"))


def _num_pair(value):
    m = re.search(r"(-?[\d,]+)\s*/\s*([\d,]+)", value)  # "1,250 / 1,500" past 999
    return (int(m[1].replace(",", "")), int(m[2].replace(",", ""))) if m else None


def hp_line(value):
    pair = _num_pair(value)
    if not pair:
        return Text.assemble(("HP ", "bold"), (value, "bright_white"))
    cur, top = pair
    ratio = cur / top if top else 1
    color = "bright_green" if ratio > 0.6 else "bright_yellow" if ratio > 0.3 else "bold bright_red"
    return Text.assemble(("HP ", "bold"), bar(ratio, color), (f" {cur}/{top}", color))


def xp_line(value, barinfo):
    num = re.match(r"[\d,]+", value)
    if not barinfo:
        return Text.assemble(("XP ", "bold"), (value, "bright_white"))
    pct, color = barinfo
    ready = color == "blue" or pct >= 100
    style = "bold bright_blue" if ready else "bright_white"
    line = Text.assemble(("XP ", "bold"), bar(pct / 100, "bright_blue" if ready else "white"),
                         (f" {pct}%", style))
    if ready:
        line.append(" ⚔ master!", "bold bright_blue")
    elif num:
        line.append(f" {num[0]}", "dim")
    return line


def gear_line(label, value, level, width):
    tag = "Wpn " if label.lower() == "weapon" else "Arm "
    lvl = f" {level[0]}/{level[1]}" if level else ""
    room = width - len(tag) - len(lvl)
    if len(value) > room:
        value = value[: max(1, room - 1)] + "…"
    return Text.assemble((tag, "dim"), (value, gear_style(*level) if level else "bright_white"), (lvl, "dim"))


def simple(label, value):
    value = re.sub(r"\s*\(\?\)$", "", value)  # "28.4 (?)": the ? is a help popup on the website
    return Text.assemble((SHORT.get(label.lower(), label) + " ", "dim"), (value, "bright_white"))


def pack(items, width):
    """Lay short items out two or three to a row in aligned columns; long ones get their own row."""
    rows, run = [], []

    def flush():
        if not run:
            return
        widest = max(t.cell_len for t in run)
        k = 3 if widest <= (width - 2) // 3 else 2 if widest <= (width - 1) // 2 else 1
        colw = (width + 1) // k
        for i in range(0, len(run), k):
            row = Text()
            for j, t in enumerate(run[i:i + k]):
                if j:
                    row.append(" " * (colw - run[i + j - 1].cell_len))
                row.append_text(t)
            rows.append(row)
        run.clear()

    for t in items:
        if t.cell_len > (width - 1) // 2:
            flush()
            if t.cell_len > width:
                t = t.copy()
                t.truncate(width, overflow="ellipsis")
            rows.append(t)
        else:
            run.append(t)
    flush()
    return rows


def sections(page):
    """[(section name, [(kind, label, value)])] in the server's order, duplicates dropped."""
    out, seen = [], set()
    name = ""
    for label, value in page.stats:
        if not value:
            name = label
            continue
        if (label, value) in seen:  # some skins list Race under two sections
            continue
        seen.add((label, value))
        if not out or out[-1][0] != name:
            out.append((name, []))
        out[-1][1].append((label, value))
    return out


def stat_lines(page, gear_level, width):
    """The sidebar as a list of Texts, each at most `width` cells."""
    if not any(v for _, v in page.stats):
        return []
    lines = []
    if page.mail and page.mail[0]:
        lines.append(Text.assemble(("✉ ", "bold bright_yellow"), (f"{page.mail[0]} new mail", "bold bright_yellow"),
                                   (" :mail", "dim")))
    for name, items in sections(page):
        if name:
            lines.append(header(name, width))
        plain = []
        for label, value in items:
            low = label.lower()
            if low == "name":
                lines.extend(pack(plain, width))
                plain = []
                t = Text(value, style="bold bright_white")
                t.truncate(width, overflow="ellipsis")
                lines.append(t)
            elif re.match(r"(hit ?points|hp|health)\b", low):
                lines.extend(pack(plain, width))
                plain = []
                lines.append(hp_line(value))
            elif re.match(r"(experience|exp)\b", low):
                lines.extend(pack(plain, width))
                plain = []
                lines.append(xp_line(value, page.bars.get(label)))
            elif low in ("weapon", "armor", "armour"):
                lines.extend(pack(plain, width))
                plain = []
                lines.append(gear_line(label, value, gear_level("weapon" if low == "weapon" else "armor", value), width))
            else:
                plain.append(simple(label, value))
        lines.extend(pack(plain, width))
    if page.mail and not page.mail[0]:
        lines.append(Text(f"✉ {page.mail[1]} old mail", style="dim"))
    return lines


def stat_summary(page, gear_level):
    """For narrow terminals: one line per category, "Category: a · b · c"."""
    out = []
    for name, items in sections(page):
        parts = []
        for label, value in items:
            low = label.lower()
            if re.match(r"(hit ?points|hp|health)\b", low):
                parts.append(hp_line(value))
            elif re.match(r"(experience|exp)\b", low):
                parts.append(xp_line(value, page.bars.get(label)))
            elif low in ("weapon", "armor", "armour"):
                parts.append(gear_line(label, value, gear_level("weapon" if low == "weapon" else "armor", value), 60))
            else:
                parts.append(simple(label, value[:39] + "…" if len(value) > 40 else value))
        line = Text.assemble((f"{name}: ", HEADER_STYLE)) if name else Text()
        out.append(line + Text(" · ", style="dim").join(parts))
    if page.mail:
        new, old = page.mail
        out.append(Text(f"✉ {new} new mail · :mail", style="bold bright_yellow") if new
                   else Text(f"✉ {old} old mail", style="dim"))
    return out
