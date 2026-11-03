# lotgdcli

Terminal client for Legend of the Green Dragon (LoTGD 2.0.x +nb Edition) web servers.
Default server: https://lotgd.popetoad.com (run by a friend of the repo owner).

## The GitHub repo is the source of truth

This project is worked on from multiple machines. https://github.com/jagger/lotgdcli
(`origin/main`) is authoritative, and any local checkout may be stale.

- **Before** reading or changing code, run `git pull --ff-only` (or `git fetch` + `git status`).
- **After** finishing a change, commit and `git push` so other machines see it.
  Don't leave finished work only in a local tree.
- If local and remote have diverged, stop and ask the user. Never force-push.
- This file is part of the repo too. Keep it updated and pushed.

## Changelog and releases

User-facing changes go under `## [Unreleased]` in `CHANGELOG.md` in the same commit.
To release: move Unreleased into a new `## [X.Y.Z] - date` section, bump `version` in
`pyproject.toml`, update the compare links at the bottom, commit, then
`git tag -a vX.Y.Z` and `git push --follow-tags`.

## Setup and run

```sh
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/lotgd -u Character          # or: .venv/bin/python -m lotgd
.venv/bin/lotgd -u Character --debug  # logs requests + saves pages to ~/.lotgdcli/cache/debug/
```

Everything the client saves lives under `~/.lotgdcli/cache/` (`lotgd/paths.py`;
`LOTGD_HOME` overrides `~/.lotgdcli`): gear levels, `:raw` dumps, and `--debug` output in
`cache/debug/`. Older checkouts saved debug pages to `./debug/`; `debug/` and `.venv/` are gitignored. Debug pages contain the user's character data,
so never commit them. They're the best input for parser bugs: read
`debug/requests.log` and the numbered HTML files.

## Layout

- `lotgd/client.py`: requests session, login, form submit, debug logging, https enforcement
- `lotgd/parser.py`: HTML → `Page` (body as rich Text, navs, forms, stats, stat bars)
- `lotgd/repl.py`: rendering (nav columns, bottom status bar) and single-key input loop
- `lotgd/colors.py`: LoTGD `col*` CSS classes → rich styles, plus `gear_style` (MMO rarity
  colors for weapon/armor level: gray/green/blue/orange, teal = shop's top item) (matched case-insensitively)
- `lotgd/credentials.py`: `load_credentials()` shared by `lotgd --login`/`-u` and lotgd-mcp:
  explicit value > `LOTGD_USER`/`LOTGD_PASSWORD` > `~/.lotgdcli/credentials` (dir 700, file 600, written
  by `lotgd --save-login`, tightened on read, migrated from `~/.config/lotgdcli/`). The
  file's password is only used for the file's own user. Plain `lotgd` stays logged out.
- `lotgd/mcp_server.py`: `lotgd-mcp` MCP server (extra `[mcp]`, mcp 2.x `MCPServer`, not v1
  `FastMCP`). Holds one Client per process. Credentials come only from env or
  `~/.lotgdcli/credentials`, never tool args. Every server hit goes through
  `_request` (rate limit + per-session cap). Keep it that way. `render()` flags
  badnav.php replays so the agent doesn't think the action happened again.
- `skills/lotgd/SKILL.md`: agent play guide + ground rules (no chat/mail/PvP unless asked).
  Installed by symlinking into `~/.claude/skills/`.

## Gotchas (learned the hard way)

- **Parse with html5lib, not html.parser.** LoTGD leaves color `<span>`s open across
  raw table output (e.g. fight health bars), so stray `</td>` tags close the main
  content cell early under html.parser, and the fight text vanishes.
- **Pin the `jade` skin** (cookie `template=legacy:jade.htm`). The parser targets its
  layout: main text is the first `td[width=100%]` under `td.headrow`, navs are
  `td.nav a.nav` with `span.navhead` section headers, and stats are `table.charinfo`
  in the `td[width=120]` column.
- **Badnav:** the server only accepts URLs offered as navs on the current page.
  Only follow hrefs from the page; never construct game URLs.
- **The server redirects to `http://` after login.** `_Session` in client.py rewrites
  same-host http URLs/redirects to https. Keep that.
- **Stat bars:** XP % comes from the expbar module's bar (`td width='NN%'`, blue =
  ready to fight your master). Read it from the HTML, don't recompute the XP formula.
- **In-text links are navs too.** Shops (weapons.php, armor.php) and lists put plain
  `<a href>` links in the main text, not `a.nav`. The renderer appends them to
  `page.navs` with `inline=True` and prints `[#n]` before them. They're reachable
  only by `#n`, never by hotkey or the single-key label-prefix fallback, so a stray
  keypress can't buy something. Links with `target` (popups) or a URL scheme are skipped.
- **Shop shortfall notes:** `annotate_shop` uses the server's rule for whether you
  can buy (cost <= on-hand Gold stat + trade-in). The trade-in comes from "give you N"
  in the text (weapons: "I'll give you N trade-in value", armor: "she'll give you N
  for them"), and the cost is the last column of a table whose `tr.trhead` ends in "Cost".
  With no "give you N", trade-in is 0, but only on weapons.php/armor.php. Elsewhere the
  match is what marks the page as one of those shops, so other "Cost" tables stay untouched.
- bs4 returns `accesskey` as a list.
- Form buttons are `(name, value, label)`: `<button>` elements post their `value` but show their
  text, so the label can differ from what's sent. Show/match buttons by `label` (`b[2]`).
- Single-key input: a non-hotkey key starts filling the first form that has a
  text/textarea field (prefilled via readline). `:` and `#` start typed commands.
- **Never let a stray key cost gold.** Forms with only hidden fields are bare buttons
  (beggarslane alms is form 1 there, ahead of the chat box). They are never the
  type-to-fill target, and `:f` asks y/N before submitting them. Pending keypresses
  are flushed (`tcflush`) before each prompt, so keys mashed during a fight don't
  land on the next page.
- **badnav.php replays the previous page's output** when the server rejects a nav or
  stale form (old `c=` counter or token). The text looks like the action happened
  again ("you hand the beggar 31 gold") but nothing changed. The REPL flags it.
- **Mail is a popup** (`mail.php`, `OVERRIDE_FORCED_NAV`): it doesn't touch the game's
  allowed navs, so the REPL (`self.game`) and MCP (`_game`) keep the game page and restore
  it on `:back` / `lotgd_mail("close")` with no request. The popup template has no sidebar,
  so `td.headrow` *is* the content cell (parser checks for `td[width=120]` first). Mail links
  are plain `<a>` (inline `#n` navs); the header's "Ye Olde Mail: N new, M old" link is
  `page.mail`. The inbox's delete form has one `msg[]` checkbox per row: values can be lists.
- **Gear levels** aren't in the sidebar (names only). `read_gear` pulls name → level from
  shop tables whose `tr.trhead` has Name + Damage/Defense; `Client` caches them per host in
  `~/.lotgdcli/cache/gear-<host>.json` (an old `~/.cache/lotgdcli` copy is migrated on load).
- Server source isn't viewable on the site; upstream is github.com/NB-Core/lotgd.

## Testing

There's no test suite yet. Verify changes by:
- Running logged out against the real server (home → `D` news), which is safe.
- Using mock pages (or saved `debug/` pages) served from a local `http.server` for
  logged-in flows. Don't create accounts or take game actions on the friend's
  server without the user asking.
- Driving the REPL through a pty for single-key input.

Keep it polite: one request per keypress, with no automation loops against the server.
