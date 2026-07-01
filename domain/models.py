"""
Domain Layer - Core data models for HUIM
Defines the fundamental data structures: Item, Transaction, UtilityEntry, UtilityList
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, FrozenSet


@dataclass
class Item:
    """Represents a single product with its profit in a transaction."""
    __slots__ = ("name", "quantity", "profit")

    name: str
    quantity: int
    profit: float  # profit per unit

    @property
    def utility(self) -> float:
        """Total utility (profit) of this item: quantity * profit_per_unit."""
        return self.quantity * self.profit

    def __repr__(self):
        return f"Item({self.name}, qty={self.quantity}, profit={self.profit}MRU)"

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return isinstance(other, Item) and self.name == other.name


@dataclass
class Transaction:
    """
    Represents a single receipt (ticket de caisse).
    Contains a list of items and the total transaction utility.
    """
    __slots__ = ("transaction_id", "items", "total_utility")

    transaction_id: int
    items: List[Item]
    total_utility: float  # sum of all item utilities in this transaction

    def get_item(self, item_name: str) -> Optional[Item]:
        """Find an item by name in this transaction."""
        for item in self.items:
            if item.name == item_name:
                return item
        return None

    def get_item_utility(self, item_name: str) -> float:
        """Get the utility of a specific item in this transaction."""
        item = self.get_item(item_name)
        return item.utility if item else 0.0

    def get_remaining_utility(self, after_item_names: List[str]) -> float:
        """
        Get the sum of utilities of items that appear AFTER the given items
        (used for UtilityList construction - 'remaining utility').
        Items are ordered as they appear in the transaction.
        """
        item_names = [item.name for item in self.items]
        # Find the last position of any of the given items
        last_pos = -1
        for name in after_item_names:
            if name in item_names:
                pos = item_names.index(name)
                last_pos = max(last_pos, pos)

        if last_pos == -1:
            return 0.0

        # Sum utilities of all items after the last position
        remaining = sum(
            self.items[i].utility
            for i in range(last_pos + 1, len(self.items))
        )
        return remaining

    def contains_all(self, item_names: List[str]) -> bool:
        """Check if this transaction contains ALL the given items."""
        transaction_item_names = {item.name for item in self.items}
        return all(name in transaction_item_names for name in item_names)

    def __repr__(self):
        items_str = ", ".join(f"{item.name}({item.utility}MRU)" for item in self.items)
        return f"Transaction(id={self.transaction_id}, [{items_str}], total={self.total_utility}MRU)"


@dataclass
class UtilityEntry:
    """
    A single entry in a UtilityList.
    Tracks how much utility an itemset contributes in one specific transaction,
    and how much 'remaining utility' exists after it in that transaction.
    """
    __slots__ = ("transaction_id", "item_utility", "remaining_utility")

    transaction_id: int
    item_utility: float      # utility of the itemset in this transaction
    remaining_utility: float  # utility of items after this itemset in the transaction

    @property
    def total_local_utility(self) -> float:
        return self.item_utility + self.remaining_utility

    def __repr__(self):
        return (f"Entry(tid={self.transaction_id}, "
                f"iutil={self.item_utility}MRU, rutil={self.remaining_utility}MRU)")


@dataclass
class UtilityList:
    """
    The 'fiche produit' (product card) for an itemset.
    Contains all transactions where the itemset appears, with utilities.

    This is the core data structure of the HUI-Miner algorithm.
    """
    itemset: FrozenSet[str]  # the set of item names (e.g., frozenset({'Caviar', 'Oeufs'}))
    entries: List[UtilityEntry] = field(default_factory=list)

    @property
    def sum_iutils(self) -> float:
        """Sum of item utilities across all transactions (actual utility of the itemset)."""
        return sum(e.item_utility for e in self.entries)

    @property
    def sum_rutils(self) -> float:
        """Sum of remaining utilities across all transactions (upper bound estimate)."""
        return sum(e.remaining_utility for e in self.entries)

    @property
    def upper_bound(self) -> float:
        """
        Upper bound on utility: sum_iutils + sum_rutils.
        If this is below MinUtil, we can prune this branch entirely.
        """
        return self.sum_iutils + self.sum_rutils

    @property
    def itemset_name(self) -> str:
        """Human-readable name for the itemset."""
        return "{" + ", ".join(sorted(self.itemset)) + "}"

    @property
    def transaction_count(self) -> int:
        """Number of transactions this itemset appears in."""
        return len(self.entries)

    def is_high_utility(self, min_util: float) -> bool:
        """Returns True if this itemset is a High Utility Itemset."""
        return self.sum_iutils >= min_util

    def can_be_pruned(self, min_util: float) -> bool:
        """Returns True if this entire branch can be pruned (no children can be HUI)."""
        return self.upper_bound < min_util

    def __repr__(self):
        return (f"UtilityList({self.itemset_name}, "
                f"iutil={self.sum_iutils:.2f}MRU, rutil={self.sum_rutils:.2f}MRU, "
                f"entries={len(self.entries)})")


@dataclass
class HUIRecord:
    """
    Lightweight summary of a discovered High Utility Itemset — used by the
    disk-backed streaming miner (core/streaming_miner.py) in place of a full
    UtilityList, since it never holds an itemset's per-transaction entries in
    RAM (those live only transiently on disk during mining).
    """
    __slots__ = ("itemset", "sum_iutils", "transaction_count")

    itemset: FrozenSet[str]
    sum_iutils: float
    transaction_count: int

    @property
    def itemset_name(self) -> str:
        return "{" + ", ".join(sorted(self.itemset)) + "}"
