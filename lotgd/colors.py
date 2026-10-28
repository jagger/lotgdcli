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


def style_for(classes):
    """Return the rich style for an element's class list, or None."""
    for cls in classes or ():
        if cls in COLORS:
            return COLORS[cls]
    return None
