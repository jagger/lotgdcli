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
lotgd --login                          # character + password from the credentials file
lotgd                                  # browse logged out (news, warrior list, ...)
lotgd --url https://other.server/ -u Name
lotgd -u Name --debug                  # see Troubleshooting
```

`--login` (`-l`) logs in as `LOTGD_USER` or the default (`user=`) character of
`~/.lotgdcli/credentials` (the same file the MCP server uses, see
[Agentic play](#agentic-play-mcp-server)). With `-u`, the password comes from
`LOTGD_PASSWORD`, then from the file if that character is saved there, else
you're asked. Plain `lotgd` never logs in on its own.

lotgd only writes your password to disk if you ask it to: `lotgd --save-login`
prompts for your character name and password (not echoed, so it stays out of
your shell history) and saves them to `~/.lotgdcli/credentials`. Run it again with `-u Other` to add
more characters: the first one saved stays the default, and the others are kept
in `[Name]` sections:

```ini
user=Main
password=...

[Alt]
password=...
```

That folder is
owner-only (700) and the file is 600. If something loosens the file's permissions,
the client tightens them back on the next read and warns. A file left at the old
`~/.config/lotgdcli/credentials` is moved there automatically. The password is
stored as plain text, protected by those permissions, the same way `~/.netrc` or
an SSH key without a passphrase is.

### The screen

On terminals at least 100 columns wide, the screen is split into three panes in a
frame exactly one screen tall, so nothing scrolls off the top:

1. **The menu** on the left (the game's "navs"), grouped by section. `[F]` means
   press **F**. A menu too long for the screen flows into two columns.
2. **The page text** in the middle, in the game's colors: village descriptions,
   fight rounds, news and so on. Enemy health bars are drawn as text bars
   (`██████░░░░`). Text longer than the pane scrolls inside it: **PgDn** / **PgUp**
   (or **Space** / **↓** / **↑**). The command bar shows where you are, as in
   `▼ lines 1–34 of 43`.
3. **Stats** on the right, grouped under the server's own categories
   (Character Info, Personal Info, Currency, Equipment Info, ...), with short
   stats packed side by side:
   - **HP** as a bar: green, then yellow, then red as it drops.
   - **XP** as a bar toward your next level. It turns blue and says
     **⚔ master!** once you have enough to challenge your master.
   - **Weapon / Armor**: colored by how good they are in the current shop tier,
     MMO style: gray, green, blue, orange, and teal for the best item the shop
     sells (level 15), with the level shown as `14/15`. The sidebar only gives
     names, so the client learns levels from the weapon and armor shop tables:
     visit MightyE's and Pegasus once (and again after a dragon kill) and the
     colors appear. Learned levels are saved in `~/.lotgdcli/cache/`, so
     you only need to see each shop's list once per machine.
   - **✉ mail**: `✉ 2 new mail :mail` in yellow at the top when you have unread mail.

Under the panes, the **command bar** holds form hints, messages (like "No [X] on
this page") and the scroll position. Messages appear there and the screen is
redrawn in place; nothing is printed below the prompt.

Narrower terminals and piped output get a stacked layout instead: page text, the
menu in columns, then one line of stats per category.

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
| `:mail` / `:m` | Open Ye Olde Mail; `:back` (or `:mail` again) returns to the game |
| PgDn / PgUp   | Scroll long page text (also Space, ↓, ↑)                   |
| `:r`          | Reload the current page                                    |
| `:motd`       | Show the message of the day                                |
| `:login`      | Log in again, e.g. after your session times out            |
| `:raw`        | Save the current page's HTML under `~/.lotgdcli/cache/raw/` |
| `:q`          | Quit                                                       |

**Forms:** on pages with a text box (bank, inn, village chat, naming things)
just start typing. Any key that isn't a menu hotkey goes into the box, and
`form N: just start typing to fill it in` under the menu tells you which form
that is. For example, at the bank press `D` for Deposit, then type `500` and
press Enter. Pages with several fields walk you through each one. Press Enter on
an empty box to keep its default, or Ctrl-C to cancel without sending anything.

Forms that are just a button, like giving alms in Beggar's Lane, never fire from
a stray key. Press them with `:f1` (as listed under `buttons:`), and confirm with `y`.

**Mashing keys is safe:** keys you press while a page is loading are thrown away,
so hammering `F` through a fight can't spill onto the victory page. If you press
a key the page no longer has, the client tells you, e.g. "There's no [F] here any
more ... the fight is over". If the server rejects an action and re-shows an
earlier page (LoTGD calls this "badnav"), the client says so. That page's
"you gave 31 gold" text is a replay, and nothing was spent again.

**Shops and other in-text links:** some pages put links in the text instead of
the menu, like the items at MightyE's Weapons or Pegasus Armor. These show up
numbered, as in `[#4] Well Crafted Bronze Sword`. Type `#4` and press Enter to
buy it. Items you can't afford aren't links on the website either, so they
don't get a number. Instead they show how much more gold you need, counting
the gold you're carrying plus the trade-in for your current weapon or armor,
as in `Golden Hilted Sword  12  6840 (need 814 more)`.

**Mail:** `:mail` opens your mailbox (the website's mail popup). Messages, Inbox,
Write, Reply and Forward are `[#n]` links. To write, open Write (or Reply), and
fill the form with `:f1`: you're asked for each field, then which button
(Send / Send and Close). Type `` `n `` in the body for a new line; on a reply,
the quoted original stays below what you type. To delete, use the Delete button
on a message, or `:f1` on the inbox and answer `y` for each message to delete.
`:back` returns to the game page you left, without a request, and its menu still works.

**Logging out:** as on the website, use the in-game quit option (for example
"Quit to the fields") before `:q`, so your character is safely logged out.

## Agentic play (MCP server)

`lotgd-mcp` is an [MCP](https://modelcontextprotocol.io) server that lets an AI
agent like Claude Code play your character with the same parser as the terminal
client. It needs Python 3.10+.

```sh
.venv/bin/pip install -e '.[mcp]'
.venv/bin/lotgd --save-login    # asks for name + password, saves ~/.lotgdcli/credentials (600)
claude mcp add --scope user lotgd -- "$PWD/.venv/bin/lotgd-mcp"
ln -s "$PWD/skills/lotgd" ~/.claude/skills/lotgd   # optional: play strategy + ground rules
```

Then ask Claude something like "play my LoTGD turns for today".

| Tool            | Does                                                         |
|-----------------|--------------------------------------------------------------|
| `lotgd_login`   | Log in as the default or a named saved character (`character`) |
| `lotgd_look`    | Show the current page (no request)                           |
| `lotgd_choose`  | Follow a hotkey (`F`), `#n` entry or in-text link, or a label |
| `lotgd_submit`  | Fill in and submit a form (field name → value)               |
| `lotgd_mail`    | `"open"` the mailbox, `"close"` to return to the game         |
| `lotgd_reload`  | Reload the current page                                      |

The password is only read from the credentials file or `LOTGD_USER` /
`LOTGD_PASSWORD`. `lotgd_login` takes a character *name* to pick one of several
saved characters, but the password is never a tool argument, so it doesn't pass through the model.
To stay polite to the server, the MCP server waits at least `LOTGD_MIN_INTERVAL`
seconds (default 1.5) between requests and stops after `LOTGD_MAX_REQUESTS`
(default 300) per session. `LOTGD_URL` and `LOTGD_DEBUG` (a directory) work like
`--url` and `--debug`.

## Troubleshooting

- **A page looks wrong or text is missing:** press `:raw` on that page. It saves
  the server's HTML and prints the file path, so you can compare it with what the
  browser shows, or attach it to an issue.
- **Something breaks over several steps:** run with `--debug` (or `--debug DIR`).
  Every request, redirect and saved page goes into `~/.lotgdcli/cache/debug/`, along with a
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
| `lotgd/mcp_server.py` | MCP server for agentic play                  |
| `skills/lotgd/`    | Claude skill: how to play + ground rules        |

## Credits

Legend of the Green Dragon is by Eric Stevens & JT Traub, with the +nb Edition by
Oliver Brendel and the NB-Core team. This is an unofficial client and isn't
affiliated with them or with any server operator. Please follow the rules of the
server you play on.
