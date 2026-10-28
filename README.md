# lotgdcli

Play [Legend of the Green Dragon](https://en.wikipedia.org/wiki/Legend_of_the_Green_Dragon)
from your terminal. lotgdcli logs in to a LoTGD web server, turns each page into
colored text, and lets you play with single keypresses, just like the hotkeys on the website.

It defaults to https://lotgd.popetoad.com, but should work with other LoTGD 2.0.x
(+nb Edition) servers via `--url`.

```
───────────────────────────────── Forest ─────────────────────────────────
~ ~ ~ Fight ~ ~ ~
You have encountered Wolf which lunges at you!
Wolf (Level 2)
Health: ██████░░░░ (9/20)
You hit Wolf for 7 points of damage!
Wolf hits you for 3 points of damage!

— Fight —                  [R]   Run
[A]   Attack               [S]   Special
──────────────────────────────────────────────────────────────────────────
HP 31/40 · XP 1,234 67% · Name Squire Maam · Level 4 · Turns 17 · Gold 230
> _
```

## Install

You need Python 3.9+ on Linux or macOS. On Windows, use WSL.

**With pipx (easiest):**

```sh
pipx install git+https://github.com/jagger/lotgdcli
lotgd -u YourCharacter
```

**From a clone:**

```sh
git clone https://github.com/jagger/lotgdcli
cd lotgdcli
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/lotgd -u YourCharacter
```

You need an existing character. Create one on the server's website first.

## Usage

```sh
lotgd -u YourCharacter                 # prompts for your password
LOTGD_PASSWORD=secret lotgd -u Name    # password from the environment
lotgd                                  # browse logged out (news, warrior list, ...)
lotgd --url https://other.server/ -u Name
lotgd -u Name --debug                  # see Troubleshooting
```

Your password is only sent to the server and never written to disk.

### The screen

Each page shows three things, top to bottom:

1. **The page text** in the game's colors: village descriptions, fight rounds,
   news and so on. Enemy health bars are drawn as text bars (`██████░░░░`).
2. **The menu** (the game's "navs"), grouped by section and laid out in columns
   to fit your terminal. `[F]` means press **F**.
3. **The status bar**, showing:
   - **HP**: green, then yellow, then red as it drops.
   - **XP**: progress toward your next level. It turns blue and says
     **⚔ fight your master!** once you have enough to challenge your master.
   - Your other stats: level, turns, gold, gems, buffs, ...

### Keys

At the `>` prompt, a single keypress acts immediately. You don't need Enter.

| Key           | Action                                                     |
|---------------|------------------------------------------------------------|
| `A`–`Z`, `0`–`9` | Follow the menu entry with that hotkey (case-insensitive) |
| `?`           | Show help                                                  |
| `Ctrl-C`      | Quit                                                       |

Start with `:` or `#` to type a longer command, then press Enter:

| Command       | Action                                                     |
|---------------|------------------------------------------------------------|
| `#3`          | Follow entry number 3: a menu entry without a hotkey, or a link in the page text |
| `:f` / `:f2`  | Fill in and submit form 1 / form 2 (or just start typing for form 1) |
| `:r`          | Reload the current page                                    |
| `:motd`       | Show the message of the day                                |
| `:login`      | Log in again, e.g. after your session times out            |
| `:raw`        | Save the current page's HTML to a temp file                |
| `:q`          | Quit                                                       |

**Forms:** on pages with an input box (bank, inn, village chat, naming things)
just start typing. `form: just start typing to fill it in` shows under the menu,
and any key that isn't a menu hotkey goes into the box. For example, at the bank
press `D` for Deposit, then type `500` and press Enter. Pages with several forms
or fields walk you through each one, and `:f2` picks form 2. Press Enter on an
empty box to keep its default.

**Shops and other in-text links:** some pages put links in the text instead of
the menu, like the items at MightyE's Weapons or Pegasus Armor. These show up
numbered, as in `[#4] Well Crafted Bronze Sword`. Type `#4` and press Enter to
buy it. Items you can't afford aren't links on the website either, so they
don't get a number. Instead they show how much more gold you need, counting
the gold you're carrying plus the trade-in for your current weapon or armor,
as in `Golden Hilted Sword  12  6840 (need 814 more)`.

**Logging out:** as on the website, use the in-game quit option (for example
"Quit to the fields") before `:q`, so your character is safely logged out.

## Troubleshooting

- **A page looks wrong or text is missing:** press `:raw` on that page. It saves
  the server's HTML and prints the file path, so you can compare it with what the
  browser shows, or attach it to an issue.
- **Something breaks over several steps:** run with `--debug` (or `--debug DIR`).
  Every request, redirect and saved page goes into `./debug/`, along with a
  `requests.log` of what the parser found on each page. Form data (and your
  password) are not logged, but the pages contain your character's info, so
  check them before sharing.
- **"You've been logged out":** the server expired your session. Type `:login`.

## How it works

LoTGD has no API, so lotgdcli works with the same HTML pages a browser gets:

- It sets the skin cookie to the classic `jade` template, so there's one known
  page layout to parse.
- Menu entries are the page's `a.nav` links, color codes become terminal colors,
  and stats come from the `charinfo` table.
- Pages are parsed with `html5lib`, because LoTGD's HTML is misnested (color tags
  stay open across tables) and only a browser-grade parser recovers the fight
  text correctly.
- The game only accepts links offered on the current page, so lotgdcli never
  builds URLs itself; it only follows the links it was given. It makes one request per
  keypress, with no automation.

Code layout:

| File               | Purpose                                         |
|--------------------|-------------------------------------------------|
| `lotgd/client.py`  | HTTP session, login, form submission, debug log |
| `lotgd/parser.py`  | HTML → page text, menu, forms, stats            |
| `lotgd/repl.py`    | Screen rendering and key handling               |
| `lotgd/colors.py`  | LoTGD color classes → terminal colors           |

## Credits

Legend of the Green Dragon is by Eric Stevens & JT Traub, with the +nb Edition by
Oliver Brendel and the NB-Core team. This is an unofficial client and isn't
affiliated with them or with any server operator. Please follow the rules of the
server you play on.
