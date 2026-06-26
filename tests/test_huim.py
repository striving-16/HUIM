"""
Tests for the HUIM project.
Run with: python -m pytest tests/ -v
Or:        python tests/test_huim.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from domain.models import Item, Transaction, UtilityEntry, UtilityList
from domain.utility_functions import (
    compute_twu_single,
    filter_by_min_util,
    build_single_item_utility_list,
    is_high_utility_itemset,
    should_explore_extensions,
)
from infrastructure.data_reader import parse_transaction_line, load_transactions_local
from core.huim_miner import HUIMiner


# ─────────────────────────────────────────────
# Fixtures: The 4 sample tickets from the PDF
# ─────────────────────────────────────────────

def make_sample_transactions():
    """Create the 4 sample transactions from the PDF document."""
    return [
        Transaction(0, [Item("Pain", 1, 1), Item("Beurre", 1, 2)], 3.0),
        Transaction(1, [Item("Pain", 1, 1), Item("Lait", 1, 1), Item("Oeufs", 1, 3)], 5.0),
        Transaction(2, [Item("Beurre", 1, 2), Item("Oeufs", 1, 3), Item("Caviar", 1, 50)], 55.0),
        Transaction(3, [Item("Pain", 1, 1), Item("Oeufs", 1, 3)], 4.0),
    ]


# ─────────────────────────────────────────────
# Domain Tests
# ─────────────────────────────────────────────

class TestItem(unittest.TestCase):

    def test_item_utility(self):
        item = Item("Caviar", 2, 50.0)
        self.assertEqual(item.utility, 100.0)

    def test_item_utility_single(self):
        item = Item("Pain", 1, 1.0)
        self.assertEqual(item.utility, 1.0)


class TestTransaction(unittest.TestCase):

    def setUp(self):
        self.t = Transaction(
            0,
            [Item("Pain", 1, 1), Item("Beurre", 1, 2), Item("Caviar", 1, 50)],
            53.0
        )

    def test_get_item_found(self):
        item = self.t.get_item("Caviar")
        self.assertIsNotNone(item)
        self.assertEqual(item.profit, 50.0)

    def test_get_item_not_found(self):
        item = self.t.get_item("Lait")
        self.assertIsNone(item)

    def test_get_item_utility(self):
        self.assertEqual(self.t.get_item_utility("Caviar"), 50.0)
        self.assertEqual(self.t.get_item_utility("Absent"), 0.0)

    def test_contains_all(self):
        self.assertTrue(self.t.contains_all(["Pain", "Caviar"]))
        self.assertFalse(self.t.contains_all(["Pain", "Lait"]))


class TestUtilityList(unittest.TestCase):

    def test_sum_iutils(self):
        ul = UtilityList(
            itemset=frozenset(["Caviar"]),
            entries=[
                UtilityEntry(0, 50.0, 5.0),
                UtilityEntry(1, 50.0, 0.0),
            ]
        )
        self.assertEqual(ul.sum_iutils, 100.0)

    def test_upper_bound(self):
        ul = UtilityList(
            itemset=frozenset(["Caviar"]),
            entries=[UtilityEntry(0, 50.0, 5.0)]
        )
        self.assertEqual(ul.upper_bound, 55.0)

    def test_is_high_utility(self):
        ul = UtilityList(
            itemset=frozenset(["Caviar"]),
            entries=[UtilityEntry(0, 50.0, 5.0)]
        )
        self.assertTrue(ul.is_high_utility(5.0))
        self.assertFalse(ul.is_high_utility(100.0))

    def test_itemset_name(self):
        ul = UtilityList(itemset=frozenset(["Caviar", "Oeufs"]), entries=[])
        self.assertEqual(ul.itemset_name, "{Caviar, Oeufs}")


# ─────────────────────────────────────────────
# Utility Function Tests
# ─────────────────────────────────────────────

class TestTWUComputation(unittest.TestCase):

    def setUp(self):
        self.transactions = make_sample_transactions()

    def test_twu_caviar(self):
        """Caviar appears only in T2 (total utility 55€) → TWU = 55€"""
        twu_map = {}
        for t in self.transactions:
            for item in t.items:
                twu_map[item.name] = twu_map.get(item.name, 0.0) + t.total_utility

        self.assertAlmostEqual(twu_map["Caviar"], 55.0)

    def test_twu_pain(self):
        """Pain appears in T0(3€), T1(5€), T3(4€) → TWU = 12€"""
        twu_map = {}
        for t in self.transactions:
            for item in t.items:
                twu_map[item.name] = twu_map.get(item.name, 0.0) + t.total_utility

        self.assertAlmostEqual(twu_map["Pain"], 12.0)

    def test_filter_by_min_util(self):
        """With MinUtil=5, Caviar(55) and Oeufs(64) should pass."""
        twu_map = {"Caviar": 55.0, "Oeufs": 64.0, "Pain": 12.0, "Beurre": 58.0, "Lait": 5.0}
        promising = filter_by_min_util(twu_map, 5.0)
        self.assertIn("Caviar", promising)
        self.assertIn("Oeufs", promising)


class TestUtilityListBuild(unittest.TestCase):

    def setUp(self):
        self.transactions = make_sample_transactions()

    def test_caviar_utility_list(self):
        """Caviar only appears in T2. Its utility is 50€."""
        ul = build_single_item_utility_list(
            "Caviar", self.transactions, ["Beurre", "Oeufs", "Caviar"]
        )
        self.assertEqual(len(ul.entries), 1)
        self.assertEqual(ul.entries[0].transaction_id, 2)
        self.assertAlmostEqual(ul.entries[0].item_utility, 50.0)

    def test_oeufs_utility_list(self):
        """Oeufs appears in T1, T2, T3."""
        ul = build_single_item_utility_list(
            "Oeufs", self.transactions, ["Beurre", "Oeufs", "Caviar"]
        )
        self.assertEqual(len(ul.entries), 3)
        tids = [e.transaction_id for e in ul.entries]
        self.assertIn(1, tids)
        self.assertIn(2, tids)
        self.assertIn(3, tids)


# ─────────────────────────────────────────────
# Infrastructure Tests
# ─────────────────────────────────────────────

class TestDataReader(unittest.TestCase):

    def test_parse_valid_line(self):
        line = "Pain:1:1 Beurre:1:2 :3"
        t = parse_transaction_line(line, 0)
        self.assertIsNotNone(t)
        self.assertEqual(len(t.items), 2)
        self.assertEqual(t.total_utility, 3.0)
        self.assertEqual(t.items[0].name, "Pain")

    def test_parse_comment_line(self):
        line = "# This is a comment"
        t = parse_transaction_line(line, 0)
        self.assertIsNone(t)

    def test_parse_empty_line(self):
        t = parse_transaction_line("", 0)
        self.assertIsNone(t)

    def test_load_sample_file(self):
        # Assumes the test is run from the project root
        filepath = os.path.join(os.path.dirname(__file__), '..', 'data', 'sample.txt')
        if os.path.exists(filepath):
            transactions = load_transactions_local(filepath)
            self.assertGreater(len(transactions), 0)


# ─────────────────────────────────────────────
# End-to-End Algorithm Test
# ─────────────────────────────────────────────

class TestHUIMinerEndToEnd(unittest.TestCase):

    def setUp(self):
        self.transactions = make_sample_transactions()

    def test_mine_with_min_util_5(self):
        """
        With MinUtil=5, from the PDF example:
        - {Caviar} has utility 50€ → HUI ✓
        - {Oeufs} has utility 9€ → HUI ✓
        - {Caviar, Oeufs} → HUI ✓
        """
        miner = HUIMiner(min_util=5.0, mode='local')
        results = miner.mine(self.transactions)

        self.assertGreater(len(results), 0)

        # Check Caviar is found
        found_caviar = any("Caviar" in ul.itemset_name and len(ul.itemset) == 1 for ul in results)
        self.assertTrue(found_caviar, "Caviar should be a HUI")

    def test_mine_with_very_high_threshold(self):
        """With MinUtil=1000, nothing should be found."""
        miner = HUIMiner(min_util=1000.0, mode='local')
        results = miner.mine(self.transactions)
        self.assertEqual(len(results), 0)

    def test_mine_caviar_utility_is_50(self):
        """The utility of {Caviar} alone should be exactly 50€."""
        miner = HUIMiner(min_util=5.0, mode='local')
        results = miner.mine(self.transactions)

        caviar_huis = [ul for ul in results if ul.itemset == frozenset(["Caviar"])]
        self.assertEqual(len(caviar_huis), 1)
        self.assertAlmostEqual(caviar_huis[0].sum_iutils, 50.0)


if __name__ == '__main__':
    print("🧪 Running HUIM Tests...\n")
    unittest.main(verbosity=2)
