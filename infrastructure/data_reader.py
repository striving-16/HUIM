"""
Infrastructure Layer - Data reading and parsing.
Handles loading transactions from files, both locally and via Spark RDDs.
"""

import os
from typing import List, Tuple, Dict, Optional, Union
from domain.models import Item, Transaction

PathLike = Union[str, os.PathLike]


# ─────────────────────────────────────────────
# File Parsing
# ─────────────────────────────────────────────

def parse_transaction_line(line: str, transaction_id: int) -> Optional[Transaction]:
    """
    Parse a single line from the input file into a Transaction.

    Expected format:
        item1:qty1:profit1 item2:qty2:profit2 ... :total_utility

    Example:
        Pain:1:1 Beurre:1:2 :3

    Lines starting with '#' are comments and are skipped.
    """
    line = line.strip()

    # Skip comments and empty lines
    if not line or line.startswith('#'):
        return None

    # Split on whitespace
    parts = line.split()

    if len(parts) < 2:
        return None

    items = []
    total_utility = 0.0

    for part in parts:
        if part.startswith(':') and len(part) > 1:
            # This is the total utility at the end: ":55"
            try:
                total_utility = float(part[1:])
            except ValueError:
                pass
        elif ':' in part:
            # This is an item: "Pain:1:1"
            sub = part.split(':')
            if len(sub) == 3:
                try:
                    name = sub[0]
                    quantity = int(sub[1])
                    profit = float(sub[2])
                    items.append(Item(name=name, quantity=quantity, profit=profit))
                except ValueError:
                    continue  # skip malformed items

    if not items:
        return None

    # If total_utility wasn't specified, compute it from items
    if total_utility == 0.0:
        total_utility = sum(item.utility for item in items)

    return Transaction(
        transaction_id=transaction_id,
        items=items,
        total_utility=total_utility
    )


def load_transactions_local(filepath: PathLike) -> List[Transaction]:
    """
    Load all transactions from a file using pure Python (no Spark).
    Used for small datasets, testing, and the DFS phase.

    `filepath` is resolved dynamically at call time — the caller (main.py,
    the FastAPI backend, tests, ...) decides which file to load. There is
    no hardcoded dataset path anywhere in this module.
    """
    filepath = os.fspath(filepath)

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Dataset file not found: {os.path.abspath(filepath)}")
    if not os.path.isfile(filepath):
        raise ValueError(f"Dataset path is not a file: {os.path.abspath(filepath)}")

    transactions = []
    tid = 0

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            transaction = parse_transaction_line(line, tid)
            if transaction is not None:
                transactions.append(transaction)
                tid += 1

    print(f"✅ Loaded {len(transactions)} transactions from '{filepath}'")
    return transactions


# ─────────────────────────────────────────────
# Spark RDD-based Loading
# ─────────────────────────────────────────────

def load_transactions_spark(filepath: PathLike, sc) -> 'RDD':
    """
    Load transactions as a Spark RDD for distributed processing.

    Returns an RDD of Transaction objects, partitioned across workers.
    This enables parallel TWU computation in Step 1.

    Args:
        filepath: path to the dataset file (dynamic, no hardcoding)
        sc: SparkContext instance
    """
    raw_rdd = sc.textFile(os.fspath(filepath))

    # Filter comments and empty lines, then parse
    # We use zipWithIndex to assign transaction IDs
    transactions_rdd = (
        raw_rdd
        .filter(lambda line: line.strip() and not line.strip().startswith('#'))
        .zipWithIndex()
        .map(lambda pair: parse_transaction_line(pair[0], pair[1]))
        .filter(lambda t: t is not None)
    )

    return transactions_rdd


def compute_twu_spark(transactions_rdd) -> Dict[str, float]:
    """
    Compute TWU for all items using Spark (distributed Step 1).

    Each transaction emits (item_name, transaction_total_utility) pairs.
    We then reduce by key to sum up TWUs across all transactions.

    Returns a dictionary: {item_name -> total_TWU}
    """
    twu_rdd = (
        transactions_rdd
        .flatMap(lambda t: [
            (item.name, t.total_utility)
            for item in t.items
        ])
        .reduceByKey(lambda a, b: a + b)
    )

    return dict(twu_rdd.collect())


def filter_transactions_spark(transactions_rdd, promising_items: List[str]):
    """
    Filter transactions to keep only promising items (after TWU pruning).
    This is Step 2 preparation — reduces data volume before UtilityList construction.

    Returns an RDD of Transaction objects with only promising items kept.
    """
    promising_set = set(promising_items)

    def keep_only_promising(transaction: Transaction) -> Transaction:
        filtered_items = [item for item in transaction.items if item.name in promising_set]
        if not filtered_items:
            return None
        new_total = sum(item.utility for item in filtered_items)
        return Transaction(
            transaction_id=transaction.transaction_id,
            items=filtered_items,
            total_utility=new_total
        )

    return (
        transactions_rdd
        .map(keep_only_promising)
        .filter(lambda t: t is not None)
    )
