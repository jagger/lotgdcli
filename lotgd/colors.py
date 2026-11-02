"""Map LoTGD color classes (from `-codes in game text) to rich styles."""

COLORS = {
    "colDkBlue": "blue",
    "colDkGreen": "green",
    "colDkCyan": "cyan",
    "colDkRed": "red",
    "colDkMagenta": "magenta",
    "colDkYellow": "yellow",
    "colDkWhite": "white",
    "colLtBlue": "bright_blue",
    "colLtGreen": "bright_green",
    "colLtCyan": "bright_cyan",
    "colLtRed": "bright_red",
    "colLtMagenta": "bright_magenta",
    "colLtYellow": "bright_yellow",
    "colLtWhite": "bright_white",
    "colLtBlack": "bright_black",
    "colDkOrange": "dark_orange3",
    "colLtOrange": "orange1",
    "colBlue": "blue1",
    "colLime": "chartreuse1",
    "colXLtGreen": "pale_green1",
    "colRose": "light_pink1",
    "colBlueViolet": "blue_violet",
    "colIceViolet": "plum1",
    "colLtBrown": "tan",
    "colDkBrown": "orange4",
    "colXLtGray": "grey85",
    "colLtGray": "grey70",
    "colDkGray": "grey42",
    "colMdGrey": "grey58",
    "colDkLinkBlue": "dodger_blue3",
    "colLtLinkBlue": "sky_blue1",
    "colMdBlue": "royal_blue1",
    "colAttention": "bold bright_red",
    "colWhiteBlack": "black on white",
    "colSaddleBrown": "orange4",
    "colBeige": "wheat1",
    "colKhaki": "khaki1",
    "colTan": "tan",
}


_BY_LOWER = {k.lower(): v for k, v in COLORS.items()}


def style_for(classes):
    """Return the rich style for an element's class list, or None. Matched
    case-insensitively: some output spells them e.g. "coliceviolet"."""
    for cls in classes or ():
        style = _BY_LOWER.get(cls.lower())
        if style:
            return style
    return None


# MMO-style gear rarity by item level within the shop's range (1..15 per dragon
# kill tier): gray, green, blue, orange, and teal for the top item.
GEAR_TIERS = (
    (4 / 15, "grey62"),
    (8 / 15, "green3"),
    (11 / 15, "dodger_blue1"),
    (1.0, "dark_orange"),
)
GEAR_MAX = "bold light_sea_green"  # teal: the best item the shop sells


def gear_style(level, top):
    if level >= top:
        return GEAR_MAX
    frac = level / top
    return next(style for limit, style in GEAR_TIERS if frac <= limit)
