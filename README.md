# 🌟 HUIM sur Spark — High Utility Itemset Mining

> Trouver les combinaisons de produits les plus rentables dans des tickets de caisse, même les rares.

---

## 🗂️ Structure du Projet

```
huim-spark/
├── domain/                  # Couche métier (zéro dépendance externe)
│   ├── models.py            # Item, Transaction, UtilityEntry, UtilityList
│   └── utility_functions.py # Fonctions mathématiques HUIM pures
│
├── core/                    # Cœur de l'algorithme
│   └── huim_miner.py        # HUI-Miner (Steps 1-4, local + Spark)
│
├── infrastructure/          # I/O et intégration Spark
│   ├── data_reader.py       # Lecture des fichiers, RDD Spark
│   └── data_writer.py       # Export CSV, TXT, console
│
├── backend/                 # API FastAPI (déployée sur Render)
│   └── app.py                # /upload, /run-huim, /results
│
├── frontend/                 # Dashboard statique (déployé sur Vercel)
│   ├── index.html
│   └── static/{css,js}/
│
├── data/
│   ├── sample.txt              # 4 tickets (exemple du document PDF), suivi par git
│   └── large_dataset_100k.txt  # Dataset 100K lignes pour les tests perf (ignoré par git)
│
├── tests/
│   └── test_huim.py         # Tests unitaires et end-to-end
│
├── results/                 # Dossier de sortie (créé automatiquement, ignoré par git)
├── main.py                  # Point d'entrée CLI (local, hors production)
├── requirements.txt
└── README.md
```

---

## 🚀 Installation & Lancement

### 1. Prérequis

- Python 3.8+
- Java 11+ (requis pour Spark)

### 2. Installer les dépendances

```bash
# Cloner / ouvrir le projet dans VS Code
cd huim-spark

# Créer un environnement virtuel (recommandé)
python -m venv venv
source venv/bin/activate        # macOS/Linux
# ou
venv\Scripts\activate           # Windows

# Installer PySpark
pip install -r requirements.txt
```

### 3. Lancer le mining

```bash
# Mode simple — données d'exemple du PDF (MinUtil = 5€)
python main.py

# Avec un dataset plus grand
python main.py --data data/large_dataset.txt --min-util 20

# Mode Spark (distribué)
python main.py --mode spark --data data/large_dataset.txt --min-util 15

# Sans sauvegarder les résultats
python main.py --no-save

# Aide
python main.py --help
```

### 4. Lancer les tests

```bash
python -m pytest tests/ -v
# ou
python tests/test_huim.py
```

---

## 📖 Comment ça Marche

### Le Problème : Fréquence ≠ Rentabilité

| Produit | Fréquence | Profit unitaire | Profit total |
|---------|-----------|-----------------|--------------|
| Pain    | 100x/jour | 0.5€            | 50€          |
| Caviar  | 2x/jour   | 50€             | **100€**     |

L'algorithme Apriori classique raterait le Caviar. **HUIM le trouve.**

### Les 4 Étapes de l'Algorithme

```
Étape 1 — TWU Filter (🔥 SPARK distribué)
   ↓  Calcule le profit potentiel max de chaque produit
   ↓  Élimine les produits sous MinUtil → réduction massive des données

Étape 2 — UtilityLists (🔥 SPARK distribué)
   ↓  Construit une "fiche produit" par item prometteur
   ↓  Chaque fiche liste : profit dans chaque ticket + profit restant

Étape 3 — DFS + Combinaisons (💻 LOCAL, peu de candidats)
   ↓  Explore les combinaisons par recherche en profondeur (DFS)
   ↓  Joint les UtilityLists deux à deux pour créer les combinaisons

Étape 4 — Sélection Finale (💻 LOCAL)
   ↓  Ne garde que les itemsets avec utilité ≥ MinUtil
   ↓  → Résultats : les combinaisons les plus rentables !
```

### Pourquoi Spark seulement pour les Étapes 1 & 2 ?

À la fin de l'Étape 2, il ne reste plus que quelques dizaines de candidats (les items vraiment prometteurs). Il est inutile de distribuer le DFS — la surcharge de communication Spark serait plus coûteuse que le calcul lui-même.

---

## 📊 Format des Données d'Entrée

Chaque ligne = un ticket de caisse :

```
item1:quantité1:profit_unitaire1  item2:quantité2:profit_unitaire2  :total
```

Exemple :
```
Pain:1:1 Beurre:1:2 :3
Caviar:1:50 Oeufs:1:3 Champagne:1:30 :83
```

---

## 📤 Résultats

Après exécution, les résultats apparaissent dans la console ET dans `results/` :

```
════════════════════════════════════════════════════════════
  🌟 RÉSULTATS — High Utility Itemsets Découverts
════════════════════════════════════════════════════════════
  Seuil MinUtil : 5.0€
  Nombre de HUI trouvés : 3
────────────────────────────────────────────────────────────
  Itemset                             Utilité (€)
────────────────────────────────────────────────────────────
  {Caviar}                                  50.00€
  {Caviar, Oeufs}                           50.00€
  {Oeufs}                                    9.00€
════════════════════════════════════════════════════════════
```

---

## 🏗️ Architecture des Couches

```
┌─────────────────────────────────────────────┐
│              main.py (CLI)                  │
└───────────────┬─────────────────────────────┘
                │
┌───────────────▼─────────────────────────────┐
│         infrastructure/                     │
│  data_reader.py    data_writer.py           │
│  (Spark I/O)       (CSV, TXT, console)      │
└───────────────┬─────────────────────────────┘
                │
┌───────────────▼─────────────────────────────┐
│              core/                          │
│         huim_miner.py                       │
│   (Steps 1-4, local + Spark dispatch)       │
└───────────────┬─────────────────────────────┘
                │
┌───────────────▼─────────────────────────────┐
│             domain/                         │
│   models.py          utility_functions.py   │
│   (Item, Transaction, (TWU, UtilityList,    │
│    UtilityList)       DFS helpers)          │
└─────────────────────────────────────────────┘
```

---

## 🔧 Ajouter vos Propres Données

Créez un fichier `.txt` dans `data/` avec le format :

```
# Mon dataset - format: item:quantite:profit :total
Produit_A:2:5.0 Produit_B:1:10.0 :20.0
Produit_C:1:100.0 Produit_A:1:5.0 :105.0
```

Puis lancez :
```bash
python main.py --data data/mon_dataset.txt --min-util 50
```

---

## 📚 Références

- Liu, M., Qu, J. (2012). *Mining High Utility Itemsets without Candidate Generation.* CIKM.
- Fournier-Viger, P. et al. (2016). *A Survey of High Utility Itemset Mining.* 
- Documentation Apache Spark : https://spark.apache.org/docs/latest/

---

## 🌐 Interface Web (Backend + Frontend)

Architecture en production :

```
Frontend (Vercel, statique) → Backend FastAPI (Render) → HUIM-Miner (Spark local) → JSON → Frontend
```

### Lancer en local

```bash
# Terminal 1 — backend FastAPI
uvicorn backend.app:app --reload --port 8000

# Terminal 2 — frontend (ouvre simplement le fichier, ou sers-le avec un serveur statique)
# frontend/index.html pointe par défaut sur http://localhost:8000
```

Ouvrir `frontend/index.html` dans le navigateur.

### Fonctionnalités du dashboard

- **📂 Données** — Charger un fichier par drag & drop (`POST /upload`)
- **⚙️ Configuration** — Régler MinUtil avec un slider, choisir le mode Local ou Spark
- **🌟 Résultats** — Tableaux triables/filtrables, graphiques interactifs (bar + donut), KPIs
- **📋 Log** — Détail complet de l'exécution de l'algorithme
- **⬇ Export** — Télécharger les résultats en CSV

---

## 🚀 Déploiement

### 1. GitHub

```bash
git add -A
git commit -m "..."
git push origin master
```

### 2. Backend sur Render

1. New **Web Service** → connecter le repo GitHub
2. Build Command : `pip install -r requirements.txt`
3. Start Command : `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`
4. Variable d'environnement `ALLOWED_ORIGINS` = l'URL Vercel du frontend (une fois connue)

⚠️ Limites du plan gratuit Render : le service s'endort après une période d'inactivité
(cold start de quelques dizaines de secondes au réveil).

### 3. Frontend sur Vercel

1. Importer le même repo GitHub — `vercel.json` sert déjà `frontend/` en statique, aucune étape de build.
2. Une fois le backend Render en ligne, éditer la ligne `window.HUIM_API_BASE` dans
   `frontend/index.html` avec l'URL Render (`https://<service>.onrender.com`), puis redéployer.

