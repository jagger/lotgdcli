---
name: lotgd
description: Play Legend of the Green Dragon (LoTGD) agentically through the lotgd MCP server (lotgd_login, lotgd_choose, lotgd_submit...). Use when the user asks to play LoTGD, run their daily turns, level up, buy gear, or check on their character.
---

# Playing LoTGD with the lotgd MCP tools

The server is a real, shared game run by a friend of the user. Play the way a careful
human would: one deliberate action at a time, and only options the page offers.

## Tools

- `lotgd_login`: log in with the configured character. Credentials come from
  `~/.config/lotgdcli/credentials`, never from you. If it says none are configured,
  tell the user and stop.
- `lotgd_look`: show the current page again (free, no request).
- `lotgd_choose`: follow a menu entry with its hotkey (`"F"`), `"#n"` for numbered
  entries and `[#n]` in-text links (shop items), or the exact label.
- `lotgd_submit`: fill a form (bank amount, inn, naming). Fields you leave out keep their defaults.
- `lotgd_reload`: refresh the page.

Every result ends with `[requests this session: n/cap]`. If you hit the cap, stop and report.

## Ground rules

- **Stick to the user's goal.** "Use my turns" means forest fights until turns run out
  or HP gets risky, not open-ended play. When the goal is done, stop and summarize.
- **No social actions unless asked.** Don't post in village/inn chat (commentary forms),
  send mail, or write bios. Those speak as the user to real people.
- **No PvP unless asked.** Don't attack other players.
- **Spending:** buying the best affordable weapon/armor upgrade, healing, and banking
  are fine when they serve the goal. Ask before spending gems or anything you can't undo
  that the user didn't ask for (e.g. selling gear, special events that cost permanent stats).
- **Unknown events:** forest special events ask you to choose. Prefer the safe or
  decline option unless the page makes the payoff clear, and mention it in your summary.
- **Log out properly** at the end: go to the village, then "Quit to the fields" (or
  sleep at the inn if you have the gold, which is safer from PvP).

## How the game works (core loop)

- **Turns** (Stats: Turns) are spent on forest fights and reset each game day
  ("Next new game day in" on the home page). A new day also restores HP.
- **Forest** (`F` from the village): "Look for something to kill" fights a creature for XP
  and gold. In a fight, `A` attacks, `R` runs (may fail), and `S` uses specialty skills.
  Prefer "Go Slumming" (weaker) when HP is low, and avoid "Go Thrillseeking" unless strong.
- **HP**: keep it above about 40% before starting a fight. Heal at the Healer's Hut in
  the forest (costs gold, cheaper when the wound is small). Dying costs the gold on
  hand and some XP, and ends the day's fighting until you're resurrected.
- **Bank** gold you aren't about to spend (bank in the village, `lotgd_submit` with an
  amount), so a death doesn't lose it.
- **Leveling**: when Experience shows "READY to fight your master", go to the warrior
  training (Bluspring's / similar in the village) and challenge your master. You
  can't level any other way, and if you put it off too long your master hunts you down.
  Heal to full first.
- **Gear**: weapons (MightyE) and armor (Pegasus) in the village. Items show their cost,
  and ones you can't afford say "(need N more)". Your current gear's trade-in counts
  toward the price. Buy the best one with a `[#n]` link if it's an upgrade.
- **Endgame**: at level 15, seek out the Green Dragon in the forest. Ask the user
  before fighting it, since winning resets the character to level 1 (with bonuses).

## Reporting back

Finish with a short summary of fights won or lost, levels gained, purchases, gold
banked, current HP/level/turns, and anything odd you skipped.
