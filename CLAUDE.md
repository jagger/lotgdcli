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

## Setup and run

```sh
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/lotgd -u Character          # or: .venv/bin/python -m lotgd
.venv/bin/lotgd -u Character --debug  # logs requests + saves pages to ./debug/
```

`debug/` and `.venv/` are gitignored. Debug pages contain the user's character data,
so never commit them. They're the best input for parser bugs: read
`debug/requests.log` and the numbered HTML files.

## Layout

- `lotgd/client.py`: requests session, login, form submit, debug logging, https enforcement
- `lotgd/parser.py`: HTML → `Page` (body as rich Text, navs, forms, stats, stat bars)
- `lotgd/repl.py`: rendering (nav columns, bottom status bar) and single-key input loop
- `lotgd/colors.py`: LoTGD `col*` CSS classes → rich styles

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
- bs4 returns `accesskey` as a list.
- Single-key input: a non-hotkey key on a page with a form starts filling form 1
  (prefilled via readline). `:` and `#` start typed commands.
- Server source isn't viewable on the site; upstream is github.com/NB-Core/lotgd.

## Testing

There's no test suite yet. Verify changes by:
- Running logged out against the real server (home → `D` news), which is safe.
- Using mock pages (or saved `debug/` pages) served from a local `http.server` for
  logged-in flows. Don't create accounts or take game actions on the friend's
  server without the user asking.
- Driving the REPL through a pty for single-key input.

Keep it polite: one request per keypress, with no automation loops against the server.
