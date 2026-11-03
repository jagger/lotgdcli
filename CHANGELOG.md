# Changelog

All notable changes to lotgdcli. Format follows [Keep a Changelog](https://keepachangelog.com/),
versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Changed
- **Stats grouped by category:** the stats pane follows the server's own sections (Character
  Info, Personal Info, Currency, Equipment Info, ...) with headers, HP and XP bars, short stats
  packed two or three to a row, and duplicate entries (Race) dropped. Unread mail sits on top.
  Narrow terminals get one line per category.
- **Prettier frame:** rounded border, matching section headers in the menu and stats, a
  one-line command bar with help on the right, and a mail popup that uses the full width.

### Added
- **Scroll long pages** inside the text pane with PgDn/PgUp (or Space, ↓, ↑). The command bar
  shows the position. A menu longer than the screen flows into two columns.

### Fixed
- **The screen no longer scrolls on an invalid key.** Messages ("No [X] on this page", errors,
  "cancelled") used to print under the prompt, pushing the top of the screen off. They now
  show in the command bar and the screen is redrawn in place. Pages taller than the screen
  no longer push the title off either.
- **Typing into a form no longer scrolls the screen either:** the page is redrawn just short
  enough that the form's prompts fit underneath it.

## [0.4.0] - 2026-11-03

### Changed
- **Three-pane screen** on terminals 100+ columns wide: the menu runs down the left, the page
  text sits in the middle, stats run down the right, and a command bar (form hints, mail hint,
  messages) is pinned above the prompt on the bottom row. On pages taller than the screen the
  menu and stats stay next to the prompt. Narrower terminals and piped output keep the old
  stacked layout.

### Fixed
- **MCP: no false "server rejected that action" warning** when a choice isn't on the page or
  `lotgd_look` re-shows a badnav page. Nothing was sent, so there's nothing to warn about.
- **MCP: logging out on purpose** ("Quit to the fields", the inn's room) now says "Logged out"
  instead of "probably a session timeout".

## [0.3.0] - 2026-11-03

### Breaking
Everything lotgdcli stores moved to `~/.lotgdcli` (`LOTGD_HOME` overrides it). Anything that
relied on the old paths needs updating, hence 0.3.0.
- **Credentials moved to `~/.lotgdcli/credentials`**, kept owner-only (folder 700, file 600,
  tightened with a warning if loosened). An existing `~/.config/lotgdcli/credentials` is
  *moved* there on first use and the old file is deleted, so scripts or an older lotgdcli
  install reading the old path won't find it. `LOTGD_CREDENTIALS` still overrides the path.
- **Saved files live in `~/.lotgdcli/cache/`:** learned gear levels (moved from
  `~/.cache/lotgdcli`, migrated automatically), `:raw` page dumps (were temp files), and the
  default `--debug` directory. `--debug` with no DIR no longer writes to `./debug`; pass
  `--debug debug` for the old behavior.

### Changed
- **Login shows progress:** a spinner says what's happening (connecting, sending the login,
  each redirect the server answers with), and the next page notes how long the login took.
  Failed logins say so with the time, too.

### Added
- **`lotgd --save-login`** prompts for character name and password (not echoed) and saves them
  owner-only, so the password never lands in shell history.

## [0.2.0] - 2026-11-03

### Added
- **MCP server and agent skill** (`lotgd-mcp`, extra `[mcp]`): login/look/choose/submit/reload
  tools for agentic play, rate-limited and capped per session. Credentials come from env or
  the credentials file, never from tool args. `skills/lotgd/SKILL.md` covers the game loop and
  ground rules for a shared server.
- **Mail:** `:mail` opens Ye Olde Mail, and `:back` returns to the game page without a request.
  The status bar shows the unread count. MCP: `lotgd_mail(open|close)`.
- **Gear colors:** the Weapon and Armor in the status bar are colored by level
  (gray/green/blue/orange, teal = the shop's best). Levels are learned from shop tables and
  cached per server.
- **Type straight into forms:** a key that isn't a menu hotkey starts filling the page's text
  form, so a bank deposit is `D`, `500`, Enter.
- **Shop links:** weapon and armor items in the page text are numbered `[#n]` and can be bought
  with `#n`. Items you can't afford show `(need N more)`, counting your trade-in.
- `lotgd --login` logs in with `LOTGD_USER`/`LOTGD_PASSWORD` or
  `~/.config/lotgdcli/credentials`. `-u` uses the file's password for that character.
- Form buttons show their real text instead of a generic "Submit".
- Typing `` `n `` in a textarea inserts a newline. Replies keep the quoted original below.

### Changed
- The screen clears between pages, so the UI no longer jumps around. Keys that don't change
  the page leave their message visible.
- Form prompts replace the `> ` line instead of printing below it.
- `:f 2` works with a space.

### Fixed
- **Stray keys can't spend gold:** button-only forms (like Beggar's Lane alms) need
  `:f<n>` plus a y/N confirm. Keys typed while a page loads are discarded, and a key from the
  previous page gets "the page has moved on".
- badnav.php replays are flagged in the REPL and MCP, so a replayed "you hand the beggar
  31 gold" isn't mistaken for a second payment.
- The session stays on https after the server's post-login redirect to http://.
- Hitpoints with thousands separators ("1,250 / 1,500") parse.
- Color classes match case-insensitively.
- Shops with no trade-in line still get shortfall notes.
- The server's PHP debug dump is stripped from page text.
- Ctrl-C at a form prompt cancels the form instead of quitting.
- Startup connection errors print a message instead of a traceback.
- Debug logs, page dumps, `:raw` and the credentials file use UTF-8 explicitly.
- MCP: a bare `"4"` picks entry #4 when 4 isn't a hotkey. `lotgd_submit` accepts
  numbers and booleans and matches options case-insensitively.

## [0.1.0] - 2026-10-28

### Added
- First release: terminal client for LoTGD 2.0.x +nb servers, with colored page text, nav
  columns, a stat bar and single-key input.

[Unreleased]: https://github.com/jagger/lotgdcli/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/jagger/lotgdcli/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/jagger/lotgdcli/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/jagger/lotgdcli/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jagger/lotgdcli/releases/tag/v0.1.0
