"""
Core Algorithm Layer - HUI-Miner implementation.

This implements the HUI-Miner algorithm using:
- Step 1 (TWU Filter): Distributed via Spark RDD
- Step 2 (UtilityList Build): Distributed via Spark RDD  
- Step 3 & 4 (DFS + Selection): Local (few candidates remain)

Reference: Liu, M., Qu, J. (2012). Mining High Utility Itemsets without Candidate Generation.
"""

import time
from typing import List, Dict, Optional, Tuple
from domain.models import Transaction, UtilityList, UtilityEntry
from domain.utility_functions import (
    compute_twu_single,
    merge_twu_maps,
    filter_by_min_util,
    build_single_item_utility_list,
    construct_utility_list,
    is_high_utility_itemset,
    should_explore_extensions,
    sort_items_by_twu,
)


class HUIMiner:
    """
    Main HUIM algorithm implementation.

    Can run in two modes:
    - 'local': pure Python, no Spark (for testing and small datasets)
    - 'spark': Steps 1 & 2 distributed via Spark (for large datasets)
    """

    def __init__(self, min_util: float, mode: str = 'local', spark_context=None):
        """
        Args:
            min_util: Minimum utility threshold (MinUtil). Only itemsets with
                      utility >= min_util are reported as HUIs.
            mode: 'local' or 'spark'
            spark_context: SparkContext (required if mode='spark')
        """
        self.min_util = min_util
        self.mode = mode
        self.sc = spark_context
        self.high_utility_itemsets: List[UtilityList] = []
        self._stats = {
            'twu_candidates': 0,
            'promising_items': 0,
            'utility_lists_built': 0,
            'dfs_nodes_explored': 0,
            'huis_found': 0,
        }

    # ─────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────

    def mine(self, transactions: List[Transaction]) -> List[UtilityList]:
        """
        Run the full HUIM algorithm on a list of transactions.

        Steps:
        1. Compute TWU for all items
        2. Prune items below MinUtil
        3. Build UtilityLists for promising items
        4. Run DFS to find all HUIs

        Returns:
            List of UtilityList objects for all discovered High Utility Itemsets.
        """
        print(f"\n🚀 Démarrage HUIM-Miner")
        print(f"   Mode        : {self.mode.upper()}")
        print(f"   MinUtil     : {self.min_util}MRU")
        print(f"   Transactions: {len(transactions)}")
        print()

        start_time = time.time()

        # ── ÉTAPE 1: TWU Filter ──
        print("📊 Étape 1 — Calcul du TWU (Transaction-Weighted Utility)...")
        twu_map = self._step1_compute_twu(transactions)
        self._stats['twu_candidates'] = len(twu_map)

        promising_items = filter_by_min_util(twu_map, self.min_util)
        promising_items = sort_items_by_twu(promising_items, twu_map)
        self._stats['promising_items'] = len(promising_items)

        print(f"   Items analysés    : {len(twu_map)}")
        print(f"   Items prometteurs : {len(promising_items)} (TWU ≥ {self.min_util}MRU)")
        if promising_items:
            print(f"   Items retenus     : {', '.join(promising_items)}")

        if not promising_items:
            print("⚠️  Aucun item prometteur trouvé. Essayez un MinUtil plus bas.")
            return []

        # ── ÉTAPE 2: Construction des UtilityLists ──
        print("\n📋 Étape 2 — Construction des UtilityLists...")
        utility_lists = self._step2_build_utility_lists(
            transactions, promising_items
        )
        self._stats['utility_lists_built'] = len(utility_lists)
        print(f"   UtilityLists construites : {len(utility_lists)}")

        # ── ÉTAPES 3 & 4: DFS + Sélection ──
        print("\n🔍 Étapes 3 & 4 — Recherche DFS + Sélection finale...")
        self.high_utility_itemsets = []
        self._dfs_search([], utility_lists, promising_items)

        elapsed = time.time() - start_time
        self._stats['huis_found'] = len(self.high_utility_itemsets)

        print(f"\n✅ Terminé en {elapsed:.3f}s")
        print(f"   Nœuds DFS explorés : {self._stats['dfs_nodes_explored']}")
        print(f"   HUI découverts      : {len(self.high_utility_itemsets)}")

        return self.high_utility_itemsets

    def get_stats(self) -> dict:
        """Return mining statistics."""
        return self._stats.copy()

    # ─────────────────────────────────────────────
    # STEP 1: TWU Computation
    # ─────────────────────────────────────────────

    def _step1_compute_twu(self, transactions: List[Transaction]) -> Dict[str, float]:
        """
        Compute TWU for all items.

        LOCAL mode: Simple Python loop over transactions.
        SPARK mode: Distributed flatMap + reduceByKey over RDD.
        """
        if self.mode == 'spark' and self.sc is not None:
            return self._step1_spark(transactions)
        else:
            return self._step1_local(transactions)

    def _step1_local(self, transactions: List[Transaction]) -> Dict[str, float]:
        """Local TWU computation — sequential Python."""
        twu_map = {}
        for transaction in transactions:
            for item in transaction.items:
                twu_map[item.name] = twu_map.get(item.name, 0.0) + transaction.total_utility
        return twu_map

    def _step1_spark(self, transactions: List[Transaction]) -> Dict[str, float]:
        """Distributed TWU computation via Spark."""
        from infrastructure.data_reader import compute_twu_spark

        print("   [Spark] Distribution du calcul TWU sur le cluster...")
        transactions_rdd = self.sc.parallelize(transactions)
        return compute_twu_spark(transactions_rdd)

    # ─────────────────────────────────────────────
    # STEP 2: UtilityList Construction
    # ─────────────────────────────────────────────

    def _step2_build_utility_lists(
        self,
        transactions: List[Transaction],
        promising_items: List[str]
    ) -> List[UtilityList]:
        """
        Build UtilityList for each promising item.

        LOCAL mode: Sequential construction.
        SPARK mode: Parallel map over promising items.
        """
        if self.mode == 'spark' and self.sc is not None:
            return self._step2_spark(transactions, promising_items)
        else:
            return self._step2_local(transactions, promising_items)

    def _step2_local(
        self,
        transactions: List[Transaction],
        promising_items: List[str]
    ) -> List[UtilityList]:
        """Local UtilityList construction — sequential Python."""
        utility_lists = []
        for item_name in promising_items:
            ul = build_single_item_utility_list(item_name, transactions, promising_items)
            utility_lists.append(ul)
            print(f"   📋 {ul}")
        return utility_lists

    def _step2_spark(
        self,
        transactions: List[Transaction],
        promising_items: List[str]
    ) -> List[UtilityList]:
        """Distributed UtilityList construction via Spark."""
        print("   [Spark] Distribution de la construction des UtilityLists...")

        # Broadcast transactions to all workers (they need the full list)
        broadcast_transactions = self.sc.broadcast(transactions)
        broadcast_promising = self.sc.broadcast(promising_items)

        items_rdd = self.sc.parallelize(promising_items)

        utility_lists_rdd = items_rdd.map(
            lambda item_name: build_single_item_utility_list(
                item_name,
                broadcast_transactions.value,
                broadcast_promising.value
            )
        )

        result = utility_lists_rdd.collect()
        for ul in result:
            print(f"   📋 {ul}")
        return result

    # ─────────────────────────────────────────────
    # STEPS 3 & 4: DFS Search
    # ─────────────────────────────────────────────

    def _dfs_search(
        self,
        prefix: List[str],
        utility_lists: List[UtilityList],
        extensions: List[str]
    ):
        """
        Recursive Depth-First Search (DFS) to explore all itemset combinations.

        For each promising item Q in extensions:
        1. Create new itemset P ∪ {Q}
        2. Build its UtilityList by joining ul_P with ul_Q
        3. If utility >= MinUtil → it's a HUI, add to results
        4. If upper_bound >= MinUtil → explore extensions (add more items)
        5. Otherwise → prune this entire branch

        Args:
            prefix: current itemset prefix (list of item names)
            utility_lists: UtilityLists corresponding to each item in prefix
            extensions: list of items that can be appended to prefix
        """
        for i, item_x in enumerate(extensions):
            self._stats['dfs_nodes_explored'] += 1

            # Find the UtilityList for the prefix P (or the empty-set UL for single items)
            # For single items: ul_px is just the UL of item_x
            ul_px = utility_lists[i]

            # ── CHECK: Is this a High Utility Itemset? ──
            if is_high_utility_itemset(ul_px, self.min_util):
                self.high_utility_itemsets.append(ul_px)
                size = len(ul_px.itemset)
                print(f"   ✨ HUI trouvé : {ul_px.itemset_name} → {ul_px.sum_iutils:.2f}MRU  (taille {size})")

            # ── CHECK: Should we explore extensions? ──
            if not should_explore_extensions(ul_px, self.min_util):
                # Prune: no extension of this itemset can be a HUI
                continue

            # ── BUILD extensions of P ∪ {X} ──
            new_prefix = prefix + [item_x]
            new_extensions = extensions[i + 1:]  # only items after X (avoid duplicates)
            new_utility_lists = []

            # Find the "parent" UL for the JOIN operation
            # For first level: parent is the empty-set UL (just sum = 0 per transaction)
            if len(prefix) == 0:
                # Parent of single item is the "empty" UL — we use a trick:
                # for single items, the JOIN reduces to simple pairing
                ul_parent = self._build_empty_ul(ul_px)
            else:
                # Find the UL of the prefix without item_x (already computed at this level)
                ul_parent = utility_lists[i]

            for item_y in new_extensions:
                # Find ul_y in the current utility_lists
                y_idx = extensions.index(item_y)
                ul_y = utility_lists[y_idx]

                # JOIN to create UL for P ∪ {X, Y}
                ul_xy = construct_utility_list(ul_px, ul_y, ul_parent)
                new_utility_lists.append(ul_xy)

            # Recurse deeper
            if new_utility_lists:
                self._dfs_search(new_prefix, new_utility_lists, new_extensions)

    def _build_empty_ul(self, ul_item: UtilityList) -> UtilityList:
        """
        Build an 'empty prefix' UtilityList for the JOIN operation at depth 1.
        The empty prefix has iutil=0 in every transaction where the item appears.
        """
        from domain.models import UtilityEntry
        entries = [
            UtilityEntry(
                transaction_id=e.transaction_id,
                item_utility=0.0,
                remaining_utility=e.item_utility + e.remaining_utility
            )
            for e in ul_item.entries
        ]
        return UtilityList(itemset=frozenset(), entries=entries)
