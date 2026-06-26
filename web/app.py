"""
Flask Web Server for HUIM on Spark Dashboard
Run: python web/app.py
Then open: http://localhost:5000
"""

import sys
import os
import json
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

from infrastructure.data_reader import load_transactions_local
from infrastructure.data_writer import generate_summary_stats
from core.huim_miner import HUIMiner

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FOLDER = os.path.join(BASE_DIR, 'data')

if os.environ.get('VERCEL'):
    UPLOAD_FOLDER = '/tmp/uploads'
    RESULTS_FOLDER = '/tmp/results'
else:
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    RESULTS_FOLDER = os.path.join(BASE_DIR, 'results')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'txt', 'csv'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/sample-datasets')
def sample_datasets():
    """Return available sample datasets."""
    datasets = []
    for fname in os.listdir(DATA_FOLDER):
        if fname.endswith('.txt'):
            fpath = os.path.join(DATA_FOLDER, fname)
            try:
                transactions = load_transactions_local(fpath)
                items = set()
                for t in transactions:
                    for item in t.items:
                        items.add(item.name)
                datasets.append({
                    'name': fname,
                    'path': fpath,
                    'transactions': len(transactions),
                    'unique_items': len(items),
                    'description': 'Dataset d\'exemple (PDF)' if 'sample' in fname else 'Dataset plus large',
                })
            except Exception:
                pass
    return jsonify(datasets)


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Handle file upload."""
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier reçu'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nom de fichier vide'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Format non supporté. Utilisez .txt ou .csv'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        transactions = load_transactions_local(filepath)
        items = set()
        for t in transactions:
            for item in t.items:
                items.add(item.name)

        return jsonify({
            'success': True,
            'filename': filename,
            'path': filepath,
            'transactions': len(transactions),
            'unique_items': len(items),
            'preview': _get_preview(transactions[:3]),
        })
    except Exception as e:
        return jsonify({'error': f'Erreur de lecture: {str(e)}'}), 400


@app.route('/api/mine', methods=['POST'])
def run_mining():
    """Run the HUIM mining algorithm."""
    data = request.get_json()
    filepath = data.get('filepath')
    min_util = float(data.get('min_util', 5.0))

    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'Fichier introuvable'}), 400

    if min_util <= 0:
        return jsonify({'error': 'MinUtil doit être > 0'}), 400

    try:
        transactions = load_transactions_local(filepath)
        start = time.time()
        miner = HUIMiner(min_util=min_util, mode='local')

        # Capture mining steps for the log
        log_lines = []
        original_print = __builtins__['print'] if isinstance(__builtins__, dict) else print

        import builtins
        captured = []
        original = builtins.print

        def capture_print(*args, **kwargs):
            line = ' '.join(str(a) for a in args)
            captured.append(line)

        builtins.print = capture_print
        try:
            results = miner.mine(transactions)
        finally:
            builtins.print = original

        elapsed = time.time() - start
        stats = generate_summary_stats(results)

        # Build itemset data for charts
        itemsets = []
        for ul in sorted(results, key=lambda x: x.sum_iutils, reverse=True):
            itemsets.append({
                'name': ul.itemset_name,
                'items': sorted(list(ul.itemset)),
                'utility': round(ul.sum_iutils, 2),
                'size': len(ul.itemset),
                'transactions': len(ul.entries),
            })

        # Compute per-item total utility
        item_utilities = {}
        for ul in results:
            for item in ul.itemset:
                item_utilities[item] = item_utilities.get(item, 0) + ul.sum_iutils

        return jsonify({
            'success': True,
            'elapsed': round(elapsed, 3),
            'itemsets': itemsets,
            'stats': stats,
            'item_utilities': item_utilities,
            'log': captured,
            'total_transactions': len(transactions),
            'min_util': min_util,
        })

    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/export', methods=['POST'])
def export_results():
    """Export results as CSV."""
    data = request.get_json()
    itemsets = data.get('itemsets', [])

    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Rang', 'Itemset', 'Utilité (€)', 'Taille', 'Transactions'])
    for i, item in enumerate(itemsets, 1):
        writer.writerow([i, item['name'], item['utility'], item['size'], item['transactions']])

    output.seek(0)
    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=huim_results.csv'}
    )


def _get_preview(transactions):
    preview = []
    for t in transactions:
        preview.append({
            'id': t.transaction_id,
            'items': [{'name': i.name, 'qty': i.quantity, 'profit': i.profit} for i in t.items],
            'total': t.total_utility,
        })
    return preview


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("╔══════════════════════════════════════════╗")
    print("║   HUIM Dashboard — Démarrage serveur     ║")
    print("╚══════════════════════════════════════════╝")
    print(f"  ➜  http://localhost:{port}")
    print()
    app.run(debug=False, host='0.0.0.0', port=port)
