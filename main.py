"""
main.py — Local testing entry point for the HUIM on Spark project.

This file is NOT the production path. In production, the FastAPI backend
(backend/app.py) calls core.huim_miner.run_huim() directly after a file
upload. This script exists purely so you can exercise run_huim() from the
command line while developing, without needing the backend running.

Usage:
    python main.py                              # Run on sample data, local mode
    python main.py --data data/large_dataset.txt --min-util 20
    python main.py --data data/sample.txt --min-util 5 --mode spark
    python main.py --help
"""

import argparse
import sys
import os

# core.huim_miner logs progress with emoji; on a non-UTF-8 console (e.g.
# Windows cp1252) that raises UnicodeEncodeError instead of just printing
# a '?'. Replace rather than crash.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

# Make sure we can import from sibling directories
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.huim_miner import run_huim
from infrastructure.data_writer import save_json_result, save_result_csv


def parse_args():
    parser = argparse.ArgumentParser(
        description="HUIM on Spark — local test runner for run_huim()",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python main.py
  python main.py --data data/large_dataset.txt --min-util 20
  python main.py --data data/sample.txt --min-util 5 --output results/
  python main.py --mode spark --data data/large_dataset.txt --min-util 15
        """
    )
    parser.add_argument(
        '--data', '-d',
        default='data/sample.txt',
        help='Chemin vers le fichier de données (défaut: data/sample.txt)'
    )
    parser.add_argument(
        '--min-util', '-u',
        type=float,
        default=5.0,
        help='Seuil minimum d\'utilité MinUtil en MRU (défaut: 5.0)'
    )
    parser.add_argument(
        '--mode', '-m',
        choices=['local', 'spark'],
        default='local',
        help='Mode d\'exécution: local (défaut) ou spark'
    )
    parser.add_argument(
        '--output', '-o',
        default='results/',
        help='Dossier de sortie pour les résultats (défaut: results/)'
    )
    parser.add_argument(
        '--no-save',
        action='store_true',
        help='Ne pas sauvegarder les résultats dans des fichiers'
    )
    return parser.parse_args()


def print_summary(result: dict):
    print("\n" + "═" * 60)
    print("  🌟 RÉSULTATS — High Utility Itemsets Découverts")
    print("═" * 60)
    print(f"  Mode          : {result['mode']}")
    print(f"  Seuil MinUtil : {result['min_util']}MRU")
    if result['elapsed_seconds'] is not None:
        print(f"  Temps d'exécution : {result['elapsed_seconds']}s")
    print(f"  Nombre de HUI trouvés : {result['huis_found']}")
    print("─" * 60)

    if not result['itemsets']:
        print("  Aucun itemset trouvé au-dessus du seuil.")
    else:
        print(f"  {'Itemset':<35} {'Utilité (MRU)':>12}")
        print("─" * 60)
        for item in result['itemsets']:
            print(f"  {item['itemset_name']:<35} {item['utility']:>12.2f}MRU")

    print("═" * 60 + "\n")

    stats = result['stats']
    if stats.get('count', 0) > 0:
        print("📈 Statistiques:")
        print(f"   Items seuls  : {stats['single_items']}")
        print(f"   Paires       : {stats['pairs']}")
        print(f"   Plus grands  : {stats['larger']}")
        print(f"   Utilité max  : {stats['max_utility']:.2f}MRU")
        print(f"   Utilité moy  : {stats['avg_utility']:.2f}MRU")


def main():
    args = parse_args()

    print("╔══════════════════════════════════════════════════════╗")
    print("║         HUIM on Spark — Mining démarré              ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"\n📂 Chargement des données depuis : {args.data}")

    try:
        result = run_huim(args.data, min_util=args.min_util, mode=args.mode)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    print_summary(result)

    if not args.no_save:
        os.makedirs(args.output, exist_ok=True)
        save_json_result(result, os.path.join(args.output, 'results.json'))
        if result['itemsets']:
            save_result_csv(result, os.path.join(args.output, 'results.csv'))

    print("\n✨ Mining terminé avec succès!\n")


if __name__ == '__main__':
    main()
