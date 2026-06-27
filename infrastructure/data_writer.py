"""
Infrastructure Layer - Results output and reporting.
Handles writing HUI results to console, CSV, and text files.
"""

import os
import csv
from typing import List, Tuple
from datetime import datetime
from domain.models import UtilityList


def print_results(results: List[UtilityList], min_util: float, elapsed_time: float = None):
    """
    Pretty-print the discovered High Utility Itemsets to the console.
    """
    print("\n" + "═" * 60)
    print("  🌟 RÉSULTATS — High Utility Itemsets Découverts")
    print("═" * 60)
    print(f"  Seuil MinUtil : {min_util}MRU")
    if elapsed_time:
        print(f"  Temps d'exécution : {elapsed_time:.3f}s")
    print(f"  Nombre de HUI trouvés : {len(results)}")
    print("─" * 60)

    if not results:
        print("  Aucun itemset trouvé au-dessus du seuil.")
    else:
        # Sort by utility descending
        sorted_results = sorted(results, key=lambda ul: ul.sum_iutils, reverse=True)
        print(f"  {'Itemset':<35} {'Utilité (MRU)':>12}")
        print("─" * 60)
        for ul in sorted_results:
            print(f"  {ul.itemset_name:<35} {ul.sum_iutils:>12.2f}MRU")

    print("═" * 60 + "\n")


def save_results_csv(results: List[UtilityList], output_path: str, min_util: float):
    """
    Save results to a CSV file.
    Columns: itemset, utility, size, items
    """
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)

    sorted_results = sorted(results, key=lambda ul: ul.sum_iutils, reverse=True)

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['itemset', 'utility_eur', 'size', 'items', 'min_util'])
        for ul in sorted_results:
            writer.writerow([
                ul.itemset_name,
                f"{ul.sum_iutils:.2f}",
                len(ul.itemset),
                ', '.join(sorted(ul.itemset)),
                min_util
            ])

    print(f"💾 Résultats sauvegardés dans : {output_path}")


def save_results_txt(results: List[UtilityList], output_path: str, min_util: float, elapsed_time: float = None):
    """
    Save a human-readable report to a text file.
    """
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)

    sorted_results = sorted(results, key=lambda ul: ul.sum_iutils, reverse=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("RAPPORT HUIM — High Utility Itemset Mining\n")
        f.write(f"Généré le : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Seuil MinUtil : {min_util}MRU\n")
        if elapsed_time:
            f.write(f"Temps d'exécution : {elapsed_time:.3f}s\n")
        f.write(f"Nombre de HUI : {len(results)}\n")
        f.write("=" * 60 + "\n\n")

        for rank, ul in enumerate(sorted_results, 1):
            f.write(f"#{rank} {ul.itemset_name}\n")
            f.write(f"   Utilité totale : {ul.sum_iutils:.2f}MRU\n")
            f.write(f"   Taille : {len(ul.itemset)} article(s)\n")
            f.write(f"   Transactions : {len(ul.entries)}\n\n")

    print(f"📄 Rapport sauvegardé dans : {output_path}")


def generate_summary_stats(results: List[UtilityList]) -> dict:
    """
    Generate summary statistics about the discovered HUIs.
    """
    if not results:
        return {"count": 0}

    utilities = [ul.sum_iutils for ul in results]
    sizes = [len(ul.itemset) for ul in results]

    return {
        "count": len(results),
        "max_utility": max(utilities),
        "min_utility": min(utilities),
        "avg_utility": sum(utilities) / len(utilities),
        "max_size": max(sizes),
        "avg_size": sum(sizes) / len(sizes),
        "single_items": sum(1 for s in sizes if s == 1),
        "pairs": sum(1 for s in sizes if s == 2),
        "larger": sum(1 for s in sizes if s > 2),
    }
