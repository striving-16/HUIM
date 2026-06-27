"""
main.py — Entry point for the HUIM on Spark project.

Usage:
    python main.py                              # Run on sample data, local mode
    python main.py --data data/large_dataset.txt --min-util 20
    python main.py --data data/sample.txt --min-util 5 --mode spark
    python main.py --help
"""

import argparse
import sys
import time
import os

# Make sure we can import from sibling directories
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.data_reader import load_transactions_local
from infrastructure.data_writer import print_results, save_results_csv, save_results_txt, generate_summary_stats
from core.huim_miner import HUIMiner


def parse_args():
    parser = argparse.ArgumentParser(
        description="HUIM on Spark — High Utility Itemset Mining",
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


def setup_spark(app_name: str = "HUIM-Spark"):
    """Initialize a SparkContext for distributed mode."""
    try:
        from pyspark import SparkContext, SparkConf
        conf = SparkConf() \
            .setAppName(app_name) \
            .setMaster("local[*]") \
            .set("spark.driver.memory", "2g")
        sc = SparkContext(conf=conf)
        sc.setLogLevel("WARN")
        print(f"✅ Spark initialisé — {sc.defaultParallelism} workers disponibles")
        return sc
    except ImportError:
        print("❌ PySpark non trouvé. Installez-le avec : pip install pyspark")
        print("   Passage en mode local...")
        return None
    except Exception as e:
        print(f"❌ Erreur Spark : {e}")
        print("   Passage en mode local...")
        return None


def main():
    args = parse_args()

    print("╔══════════════════════════════════════════════════════╗")
    print("║         HUIM on Spark — Mining démarré              ║")
    print("╚══════════════════════════════════════════════════════╝")

    # ── Setup Spark if needed ──
    sc = None
    mode = args.mode
    if mode == 'spark':
        sc = setup_spark()
        if sc is None:
            mode = 'local'
            print("   ⚠️  Basculement en mode LOCAL\n")

    # ── Load Data ──
    print(f"\n📂 Chargement des données depuis : {args.data}")
    try:
        transactions = load_transactions_local(args.data)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    if not transactions:
        print("❌ Aucune transaction trouvée dans le fichier.")
        sys.exit(1)

    # ── Run HUIM Mining ──
    miner = HUIMiner(
        min_util=args.min_util,
        mode=mode,
        spark_context=sc
    )

    start = time.time()
    results = miner.mine(transactions)
    elapsed = time.time() - start

    # ── Display Results ──
    print_results(results, args.min_util, elapsed)

    # ── Save Results ──
    if not args.no_save and results:
        os.makedirs(args.output, exist_ok=True)
        save_results_csv(results, os.path.join(args.output, 'results.csv'), args.min_util)
        save_results_txt(results, os.path.join(args.output, 'report.txt'), args.min_util, elapsed)

    # ── Summary Stats ──
    stats = generate_summary_stats(results)
    if stats.get('count', 0) > 0:
        print("📈 Statistiques:")
        print(f"   Items seuls  : {stats['single_items']}")
        print(f"   Paires       : {stats['pairs']}")
        print(f"   Plus grands  : {stats['larger']}")
        print(f"   Utilité max  : {stats['max_utility']:.2f}MRU")
        print(f"   Utilité moy  : {stats['avg_utility']:.2f}MRU")

    # ── Stop Spark ──
    if sc is not None:
        sc.stop()
        print("\n✅ Spark arrêté.")

    print("\n✨ Mining terminé avec succès!\n")


if __name__ == '__main__':
    main()
