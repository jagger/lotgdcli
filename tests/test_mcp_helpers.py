"""Offline checks for the MCP server's pure helpers (run: python -m unittest)."""
import unittest

from lotgd.mcp_server import pick_heal, status_of


class FakePage:
    def __init__(self, stats, bars=None, mail=None, title="Village"):
        self.stats, self.bars, self.mail, self.title = stats, bars or {}, mail, title


class PickHeal(unittest.TestCase):
    OPTS = {10: 16, 50: 81, 70: 113, 100: None}

    def test_percent_of_missing_hp(self):
        # 65/122, target 75% = 92 HP: needs 27 of 57 missing = 47% -> the 50% potion
        self.assertEqual(pick_heal(65, 122, 75, {10: 16, 50: 81, 100: None}), (50, 81))

    def test_already_there(self):
        self.assertIsNone(pick_heal(120, 122, 75, self.OPTS))

    def test_full_heal(self):
        self.assertEqual(pick_heal(10, 100, 100, self.OPTS), (100, None))

    def test_nothing_reaches(self):
        self.assertIsNone(pick_heal(10, 100, 100, {10: 1}))


class Status(unittest.TestCase):
    def test_parse(self):
        p = FakePage([("Level", "11"), ("Hitpoints", "110 / 122"), ("Gold", "1,234"),
                      ("Bankgold", "3,755"), ("Race", "Dwarf"), ("Race", "Dwarf"),
                      ("Buffs", "Stallion Attack (37 rounds left)")],
                     bars={"Experience": (100, "blue")}, mail=(2, 1))
        s = status_of(p)
        self.assertEqual((s["level"], s["hp"], s["max_hp"], s["gold"], s["bank"]), (11, 110, 122, 1234, 3755))
        self.assertTrue(s["ready_for_master"])
        self.assertEqual(s["mail_new"], 2)
        self.assertIn("37 rounds", s["buffs"])


if __name__ == "__main__":
    unittest.main()
