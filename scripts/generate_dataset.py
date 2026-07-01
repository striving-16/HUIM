"""
scripts/generate_dataset.py — Synthetic transaction dataset generator for HUIM load testing.

Produces files in the same format core.huim_miner / infrastructure.data_reader expect:
    item:quantity:profit item2:quantity2:profit2 ... :total_utility

Usage:
    python scripts/generate_dataset.py --rows 1000000 --output data/large_dataset_1m.txt
"""

import argparse
import random

# Same item pool as data/large_dataset_100k.txt, for consistency across dataset sizes.
# (item_name, min_profit, max_profit) — cheap staples vs. rare/expensive items, so
# HUIM has both high-frequency/low-utility and low-frequency/high-utility items to find.
ITEMS = [
    ("Pain", 0.5, 1.5),
    ("Riz", 1.0, 2.0),
    ("Lait", 0.5, 1.2),
    ("The", 2.0, 3.5),
    ("Oeufs", 2.5, 3.5),
    ("Beurre", 1.5, 2.5),
    ("Sucre", 0.8, 1.5),
    ("Huile", 3.0, 5.0),
    ("Fromage", 4.0, 7.0),
    ("Bissap", 1.0, 2.0),
    ("Poulet", 8.0, 15.0),
    ("Agneau", 20.0, 40.0),
    ("Miel", 15.0, 25.0),
    ("Dattes", 30.0, 60.0),
    ("Encens", 10.0, 20.0),
]


def generate_transaction(rng: random.Random) -> str:
    basket_size = rng.randint(1, 6)
    chosen = rng.sample(ITEMS, k=min(basket_size, len(ITEMS)))

    parts = []
    total = 0.0
    for name, lo, hi in chosen:
        quantity = rng.randint(1, 5)
        profit = round(rng.uniform(lo, hi), 2)
        parts.append(f"{name}:{quantity}:{profit}")
        total += quantity * profit

    parts.append(f":{round(total, 2)}")
    return " ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Generate a synthetic HUIM transaction dataset.")
    parser.add_argument("--rows", type=int, default=1_000_000, help="Number of transactions to generate")
    parser.add_argument("--output", default="data/large_dataset_1m.txt", help="Output file path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(f"# Format: item:quantity:profit item:quantity:profit ... : total_utility\n")
        f.write(f"# Synthetic dataset — {args.rows} transactions, generated for load testing\n")
        for _ in range(args.rows):
            f.write(generate_transaction(rng) + "\n")

    print(f"Wrote {args.rows} transactions to {args.output}")


if __name__ == "__main__":
    main()
