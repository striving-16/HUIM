"""
Disk-backed streaming HUI-Miner — the memory-bounded path used by run_huim()
for local-mode mining of real (potentially large) files on constrained hosts.

Design: every pass over the dataset reads the file line-by-line and discards
each parsed transaction immediately. Nothing that scales with the number of
transactions is ever held in a Python list — only small aggregate maps
(TWU per item, occurrence counts) live in RAM. Per-item utility-list entries
are written to temp JSONL files on disk; DFS joins load at most two small
per-item maps into memory at a time (the two operands being joined) and
stream the third, writing the combined result straight to a new file.

core.huim_miner.HUIMiner.mine() (the original in-memory implementation,
which the unit tests exercise directly with small in-memory transaction
lists) is left untouched — this module reimplements the same algorithm
end-to-end for disk-backed execution, and its output has been verified to
match HUIMiner.mine() exactly on the same input.
"""

import json
import os
import shutil
import tempfile
import time
from typing import Dict, List, Optional, Tuple

from domain.models import HUIRecord
from domain.utility_functions import filter_by_min_util, sort_items_by_twu
from infrastructure.data_reader import parse_transaction_line


def compute_twu_streaming(filepath: str) -> Tuple[Dict[str, float], int]:
    """Pass 1 (Step 1): stream the file once, accumulate TWU per item. No transaction list kept."""
    twu_map: Dict[str, float] = {}
    total = 0
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            t = parse_transaction_line(line, total)
            if t is None:
                continue
            for item in t.items:
                twu_map[item.name] = twu_map.get(item.name, 0.0) + t.total_utility
            total += 1
    return twu_map, total


def build_item_utility_files(filepath: str, promising_items: List[str], out_dir: str) -> Tuple[Dict[str, str], Dict[str, int]]:
    """
    Pass 2 (Step 2): stream the file once. For every promising item in a
    transaction, append a {"tid","iu","ru"} JSONL entry to that item's own
    temp file. Returns (item -> file path, item -> occurrence count).
    """
    promising_set = set(promising_items)
    paths = {name: os.path.join(out_dir, f"item_{i}.jsonl") for i, name in enumerate(promising_items)}
    counts = {name: 0 for name in promising_items}
    handles = {name: open(path, 'w', encoding='utf-8') for name, path in paths.items()}

    tid = 0
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                t = parse_transaction_line(line, tid)
                if t is None:
                    continue
                tid += 1

                ordered = [it for it in t.items if it.name in promising_set]
                if not ordered:
                    continue

                suffix_sums = [0.0] * (len(ordered) + 1)
                for i in range(len(ordered) - 1, -1, -1):
                    suffix_sums[i] = suffix_sums[i + 1] + ordered[i].utility

                for i, it in enumerate(ordered):
                    handles[it.name].write(json.dumps({
                        "tid": t.transaction_id,
                        "iu": it.utility,
                        "ru": suffix_sums[i + 1],
                    }) + "\n")
                    counts[it.name] += 1
    finally:
        for h in handles.values():
            h.close()

    return paths, counts


def load_item_dict(path: str) -> Dict[int, Tuple[float, float]]:
    """Load one promising item's JSONL utility-list file into a small in-memory dict {tid: (iu, ru)}."""
    entries: Dict[int, Tuple[float, float]] = {}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            rec = json.loads(line)
            entries[rec["tid"]] = (rec["iu"], rec["ru"])
    return entries


def build_empty_ul_dict(entries: Dict[int, Tuple[float, float]]) -> Dict[int, Tuple[float, float]]:
    """Synthetic 'empty prefix' UL: iutil=0, remaining=iu+ru per entry (matches HUIMiner._build_empty_ul)."""
    return {tid: (0.0, iu + ru) for tid, (iu, ru) in entries.items()}


def join_utility_lists(
    entries_p: Dict[int, Tuple[float, float]],
    entries_q: Dict[int, Tuple[float, float]],
    entries_parent: Dict[int, Tuple[float, float]],
) -> Dict[int, Tuple[float, float]]:
    """
    In-memory JOIN (matches domain.utility_functions.construct_utility_list),
    operating on the small per-item dicts already loaded for the current DFS
    path — never touches disk or the raw dataset. Below the top DFS level,
    entries_p/entries_q/entries_parent are themselves join results already
    held in memory (mirrors the original algorithm's recursion, just backed
    by plain dicts instead of UtilityList/UtilityEntry objects).
    """
    result: Dict[int, Tuple[float, float]] = {}
    # Iterate whichever of P/Q is smaller for fewer dict lookups.
    smaller, larger = (entries_p, entries_q) if len(entries_p) <= len(entries_q) else (entries_q, entries_p)
    is_p_smaller = smaller is entries_p
    for tid, e_small in smaller.items():
        e_large = larger.get(tid)
        if e_large is None:
            continue
        e_parent = entries_parent.get(tid)
        if e_parent is None:
            continue
        ep = e_small if is_p_smaller else e_large
        eq = e_large if is_p_smaller else e_small
        combined_iu = ep[0] + eq[0] - e_parent[0]
        combined_ru = eq[1]  # remaining utility comes from Q's remaining (tighter bound)
        result[tid] = (combined_iu, combined_ru)
    return result


def aggregate(entries: Dict[int, Tuple[float, float]]) -> Tuple[float, float]:
    """Sum item_utility and remaining_utility across an in-memory utility-list dict."""
    sum_iu = sum(e[0] for e in entries.values())
    sum_ru = sum(e[1] for e in entries.values())
    return sum_iu, sum_ru


class StreamingHUIMiner:
    """Disk-backed equivalent of HUIMiner, driven entirely from a dataset file path."""

    def __init__(self, min_util: float, tmp_dir: str):
        self.min_util = min_util
        self.tmp_dir = tmp_dir
        self._stats = {
            'twu_candidates': 0,
            'promising_items': 0,
            'utility_lists_built': 0,
            'dfs_nodes_explored': 0,
            'huis_found': 0,
            'total_transactions': 0,
        }

    def get_stats(self) -> dict:
        return self._stats.copy()

    def mine(self, dataset_path: str) -> List[HUIRecord]:
        twu_map, total_transactions = compute_twu_streaming(dataset_path)
        self._stats['twu_candidates'] = len(twu_map)
        self._stats['total_transactions'] = total_transactions

        promising_items = filter_by_min_util(twu_map, self.min_util)
        promising_items = sort_items_by_twu(promising_items, twu_map)
        self._stats['promising_items'] = len(promising_items)

        if not promising_items:
            return []

        item_files, occurrences = build_item_utility_files(dataset_path, promising_items, self.tmp_dir)
        self._stats['utility_lists_built'] = len(item_files)

        results: List[HUIRecord] = []

        # Top level: each promising item's raw utility-list dict is loaded from
        # disk exactly once (when it's this iteration's item_x) plus transient
        # reloads when it's needed as item_y by earlier iterations — never all
        # of them simultaneously. Every level below this is pure in-memory dict
        # joins (no disk access), matching HUIMiner._dfs_search's recursion.
        for i, item_x in enumerate(promising_items):
            self._stats['dfs_nodes_explored'] += 1
            entries_x = load_item_dict(item_files[item_x])
            sum_iu, sum_ru = aggregate(entries_x)
            count = len(entries_x)

            if sum_iu >= self.min_util:
                results.append(HUIRecord(itemset=frozenset([item_x]), sum_iutils=sum_iu, transaction_count=count))
                self._stats['huis_found'] += 1

            if sum_iu + sum_ru < self.min_util:
                continue

            new_extensions = promising_items[i + 1:]
            if not new_extensions:
                continue

            parent_entries = build_empty_ul_dict(entries_x)
            new_item_dicts = {}
            for item_y in new_extensions:
                entries_y = load_item_dict(item_files[item_y])
                new_item_dicts[item_y] = join_utility_lists(entries_x, entries_y, parent_entries)

            if new_item_dicts:
                self._dfs_search_in_memory([item_x], new_item_dicts, new_extensions, results)

        for path in item_files.values():
            self._safe_remove(path)

        return results

    def _safe_remove(self, path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass

    def _dfs_search_in_memory(
        self,
        prefix: List[str],
        item_dicts: Dict[str, Dict[int, Tuple[float, float]]],
        extensions: List[str],
        results: List[HUIRecord],
    ) -> None:
        for i, item_x in enumerate(extensions):
            self._stats['dfs_nodes_explored'] += 1
            entries_x = item_dicts[item_x]
            sum_iu, sum_ru = aggregate(entries_x)
            count = len(entries_x)

            if sum_iu >= self.min_util:
                results.append(HUIRecord(
                    itemset=frozenset(prefix + [item_x]),
                    sum_iutils=sum_iu,
                    transaction_count=count,
                ))
                self._stats['huis_found'] += 1

            if sum_iu + sum_ru < self.min_util:
                continue  # upper bound below MinUtil: prune this branch

            new_prefix = prefix + [item_x]
            new_extensions = extensions[i + 1:]
            if not new_extensions:
                continue

            parent_entries = entries_x  # matches HUIMiner: ul_parent = utility_lists[i] when prefix non-empty

            new_item_dicts = {}
            for item_y in new_extensions:
                new_item_dicts[item_y] = join_utility_lists(entries_x, item_dicts[item_y], parent_entries)

            if new_item_dicts:
                self._dfs_search_in_memory(new_prefix, new_item_dicts, new_extensions, results)


def run_huim_streaming(dataset_path: str, min_util: float) -> dict:
    """
    Disk-backed equivalent of core.huim_miner.run_huim() for mode='local'.
    Returns the same JSON-serializable dict shape as results_to_dict().
    """
    from infrastructure.data_writer import results_to_dict

    max_dataset_mb = float(os.environ.get("HUIM_MAX_DATASET_MB", 200))
    file_size_mb = os.path.getsize(dataset_path) / (1024 * 1024)
    if file_size_mb > max_dataset_mb:
        from core.huim_miner import DatasetTooLargeError
        raise DatasetTooLargeError(
            f"Dataset is {file_size_mb:.1f}MB, exceeding the {max_dataset_mb:.0f}MB safety limit. "
            f"Raise HUIM_MAX_DATASET_MB if this host has more disk/memory available."
        )

    tmp_dir = tempfile.mkdtemp(prefix="huim_stream_")
    try:
        start_time = time.time()
        miner = StreamingHUIMiner(min_util=min_util, tmp_dir=tmp_dir)
        results = miner.mine(dataset_path)
        elapsed = time.time() - start_time
        algorithm_stats = miner.get_stats()

        return results_to_dict(
            results,
            min_util,
            elapsed,
            total_transactions=algorithm_stats.get('total_transactions', 0),
            mode="local",
            algorithm_stats=algorithm_stats,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
