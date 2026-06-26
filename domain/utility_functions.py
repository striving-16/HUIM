"""
Domain Layer - Pure utility functions for HUIM calculations.
No Spark dependency here — pure Python math and logic.
"""

from typing import List, Dict, Tuple, FrozenSet
from domain.models import Transaction, Item, UtilityEntry, UtilityList


# ─────────────────────────────────────────────
# TWU (Transaction-Weighted Utility) Functions
# ─────────────────────────────────────────────

def compute_twu_single(transaction: Transaction) -> Dict[str, float]:
    """
    Compute the TWU contribution of a single transaction.
    Each item in the transaction gets credited with the FULL transaction utility.

    Why? Because the TWU is an upper bound: if item X appears in a transaction
    worth 55€, then X can at most contribute 55€ in any itemset involving that transaction.
    """
    twu_contributions = {}
    for item in transaction.items:
        twu_contributions[item.name] = transaction.total_utility
    return twu_contributions


def merge_twu_maps(map1: Dict[str, float], map2: Dict[str, float]) -> Dict[str, float]:
    """Merge two TWU maps by summing values for shared keys."""
    merged = dict(map1)
    for item_name, twu in map2.items():
        merged[item_name] = merged.get(item_name, 0.0) + twu
    return merged


def filter_by_min_util(twu_map: Dict[str, float], min_util: float) -> List[str]:
    """
    Return only item names whose TWU meets or exceeds min_util.
    Items below this threshold can NEVER be part of a HUI — safe to prune.
    """
    return [name for name, twu in twu_map.items() if twu >= min_util]


# ─────────────────────────────────────────────
# UtilityList Construction Functions
# ─────────────────────────────────────────────

def build_single_item_utility_list(
    item_name: str,
    transactions: List[Transaction],
    promising_items: List[str]
) -> UtilityList:
    """
    Build the UtilityList for a single item.

    For each transaction containing this item:
    - item_utility = utility of this item in the transaction
    - remaining_utility = sum of utilities of promising items that appear AFTER this item
    """
    entries = []

    for transaction in transactions:
        item = transaction.get_item(item_name)
        if item is None:
            continue  # item not in this transaction

        # Get ordered list of item names in this transaction
        ordered_names = [i.name for i in transaction.items]
        item_pos = ordered_names.index(item_name)

        # Remaining utility = sum of utilities of promising items after this item
        remaining = sum(
            transaction.get_item_utility(name)
            for i, name in enumerate(ordered_names)
            if i > item_pos and name in promising_items
        )

        entries.append(UtilityEntry(
            transaction_id=transaction.transaction_id,
            item_utility=item.utility,
            remaining_utility=remaining
        ))

    return UtilityList(itemset=frozenset([item_name]), entries=entries)


def construct_utility_list(
    ul_p: UtilityList,
    ul_q: UtilityList,
    ul_pq_parent: UtilityList
) -> UtilityList:
    """
    Construct the UtilityList for itemset P∪Q from:
    - ul_p: UtilityList of prefix P
    - ul_q: UtilityList of item Q
    - ul_pq_parent: UtilityList of the parent itemset (P without last element)

    This is the core JOIN operation in HUI-Miner.
    Only transactions present in BOTH ul_p and ul_q are included.
    """
    new_itemset = ul_p.itemset | ul_q.itemset
    entries = []

    # Index entries by transaction_id for fast lookup
    p_by_tid = {e.transaction_id: e for e in ul_p.entries}
    q_by_tid = {e.transaction_id: e for e in ul_q.entries}
    parent_by_tid = {e.transaction_id: e for e in ul_pq_parent.entries}

    # Only consider transactions where BOTH P and Q appear
    common_tids = set(p_by_tid.keys()) & set(q_by_tid.keys())

    for tid in sorted(common_tids):
        ep = p_by_tid[tid]
        eq = q_by_tid[tid]
        eparent = parent_by_tid.get(tid)

        if eparent is None:
            continue

        # Combined item utility = ep.iutil + eq.iutil - eparent.iutil
        # (avoids double-counting the shared prefix)
        combined_iutil = ep.item_utility + eq.item_utility - eparent.item_utility

        # Remaining utility comes from Q's remaining (it's the tighter bound)
        combined_rutil = eq.remaining_utility

        entries.append(UtilityEntry(
            transaction_id=tid,
            item_utility=combined_iutil,
            remaining_utility=combined_rutil
        ))

    return UtilityList(itemset=new_itemset, entries=entries)


# ─────────────────────────────────────────────
# Pruning & Validation
# ─────────────────────────────────────────────

def is_high_utility_itemset(utility_list: UtilityList, min_util: float) -> bool:
    """Check if an itemset qualifies as a High Utility Itemset."""
    return utility_list.sum_iutils >= min_util


def should_explore_extensions(utility_list: UtilityList, min_util: float) -> bool:
    """
    Check if we should explore extensions of this itemset (add more items).
    If the upper bound (iutil + rutil) < min_util, no extension can be HUI → prune.
    """
    return utility_list.upper_bound >= min_util


def sort_items_by_twu(items: List[str], twu_map: Dict[str, float]) -> List[str]:
    """Sort items by TWU in ascending order (standard HUI-Miner ordering)."""
    return sorted(items, key=lambda x: twu_map.get(x, 0.0))
