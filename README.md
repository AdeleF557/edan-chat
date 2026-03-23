# 🗳️ EDAN 2025 — Chat avec les résultats électoraux

> Application de chat permettant d'interroger en langage naturel les résultats
> des élections législatives ivoiriennes du 27 décembre 2025.











---

## 📋 Table des matières

1. [Ce que fait l'application](#ce-que-fait-lapplication)
2. [Prérequis](#prérequis)
3. [Installation pas à pas](#installation-pas-à-pas)
4. [Lancer l'application](#lancer-lapplication)
5. [Utiliser le chat](#utiliser-le-chat)
6. [Structure du projet](#structure-du-projet)
7. [Résolution de problèmes](#résolution-de-problèmes)

---

## Ce que fait l'application

Vous posez une question en français dans un chat, et l'application :

1. **Comprend** votre question grâce à GPT-4o (OpenAI)
2. **Traduit** votre question en requête SQL
3. **Interroge** la base de données issue du PDF officiel de la CEI
4. **Répond** avec un texte clair + un tableau de données + un graphique

**Exemples de questions que vous pouvez poser :**

| Question | Type de réponse |
|---|---|
| Combien de sièges le RHDP a-t-il obtenus ? | Chiffre + tableau |
| Top 10 des candidats avec le plus de voix | Classement |
| Taux de participation par région | Tableau + graphique en barres |
| Histogramme des gagnants par parti | Graphique en camembert |
| Qui a gagné dans la circonscription d'Agboville ? | Réponse factuelle |
| Quels candidats indépendants ont été élus ? | Liste filtrée |

---

## Prérequis

Avant de commencer, vous avez besoin de :

### 1. Python 3.10 ou plus récent

Vérifiez votre version en ouvrant un terminal et en tapant :
```bash
python --version
# ou
python3 --version
```

Si Python n'est pas installé :
- **Windows** : téléchargez sur [python.org](https://www.python.org/downloads/)
- **Mac** : `brew install python` (si vous avez Homebrew)
- **Linux** : `sudo apt install python3`

### 2. Une clé API OpenAI

- Allez sur [platform.openai.com](https://platform.openai.com)
- Créez un compte ou connectez-vous
- Cliquez sur votre profil → **API keys** → **Create new secret key**
- Copiez la clé (elle ressemble à `sk-proj-...`)
- ⚠️ **Important** : vous ne pourrez plus la voir après, gardez-la précieusement

### 3. Le fichier PDF des résultats

Téléchargez le PDF officiel depuis le site de la CEI :
```
https://www.cei.ci/wp-content/uploads/2025/12/EDAN_2025_RESULTAT_NATIONAL_DETAILS.pdf
```
Vous le placerez dans le dossier `data/` à l'étape suivante.

---

## Installation pas à pas

### Étape 1 — Télécharger le projet

Si vous avez Git :
```bash
git clone https://github.com/AdeleF557/edan-chat.git
cd edan-chat
```

Si vous n'avez pas Git, téléchargez le ZIP du projet et décompressez-le,
puis ouvrez un terminal dans le dossier décompressé.

---

### Étape 2 — Créer un environnement virtuel Python

Un environnement virtuel isole les dépendances du projet
pour ne pas interférer avec votre Python système.
```bash
# Créer l'environnement virtuel
python -m venv venv

# L'activer :
# Sur Windows :
venv\Scripts\activate

# Sur Mac / Linux :
source venv/bin/activate
```

✅ Vous devriez voir `(venv)` apparaître au début de votre ligne de commande.

---

### Étape 3 — Installer les dépendances
```bash
pip install -r requirements.txt
```

Cette commande installe automatiquement toutes les bibliothèques nécessaires
(OpenAI, Streamlit, DuckDB, pdfplumber, etc.).

Cela peut prendre 2 à 3 minutes la première fois.

---

### Étape 4 — Configurer votre clé API

Copiez le fichier exemple de configuration :
```bash
# Sur Mac / Linux :
cp .env.example .env

# Sur Windows :
copy .env.example .env
```

Ouvrez le fichier `.env` avec n'importe quel éditeur de texte
(Notepad, TextEdit, VS Code...) et remplacez la valeur :
```
# Avant :
OPENAI_API_KEY=sk-VOTRE_CLE_OPENAI_ICI
x
^X

# Après (exemple) :
OPENAI_API_KEY=sk-proj-abc123...votrevraieclé
```

Sauvegardez le fichier.

---

### Étape 5 — Placer le PDF dans le dossier data/
```bash
# Créer le dossier data/ s'il n'existe pas
mkdir -p data

# Copiez le PDF téléchargé dans ce dossier
# Le fichier doit s'appeler exactement :
# EDAN_2025_RESULTAT_NATIONAL_DETAILS.pdf
```

Votre dossier `data/` doit ressembler à ceci :
```
data/
└── EDAN_2025_RESULTAT_NATIONAL_DETAILS.pdf
```

---

### Étape 6 — Initialiser la base de données

Cette étape extrait les données du PDF et les charge en base.
Elle ne se fait qu'une seule fois (environ 1 à 2 minutes).
```bash
make ingest
# ou si make n'est pas disponible sur Windows :
python -c "from ingestion.load import run_ingestion_pipeline; from app.config import PDF_PATH; run_ingestion_pipeline(PDF_PATH)"
```

Vous devriez voir dans le terminal :
```
📄 Extraction du PDF...
   → 2800 lignes brutes extraites
🧹 Transformation et nettoyage...
   → 2750 lignes après nettoyage
💾 Chargement en base DuckDB...
   → 2750 lignes en base
```

✅ La base de données est prête.

---

## Lancer l'application
```bash
make run
# ou :
streamlit run app/app.py
```

Votre navigateur s'ouvre automatiquement sur :
```
http://localhost:8501
```

Si le navigateur ne s'ouvre pas, copiez-collez cette adresse manuellement.

---

## Utiliser le chat

### Interface principale
```
┌─────────────────────────────────────────────────────────┐
│  Sidebar gauche          │  Zone de chat principale      │
│                          │                               │
│  ✅ Base prête           │  💬 Historique des messages   │
│                          │                               │
│  🔍 Afficher le SQL      │  [Message assistant d'accueil]│
│     (toggle on/off)      │                               │
│                          │  [Vos questions + réponses]   │
│                          │                               │
│                          │  ┌─────────────────────────┐ │
│                          │  │ Tapez votre question... │ │
│                          │  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Poser une question

1. Cliquez dans le champ de saisie en bas
2. Tapez votre question en français
3. Appuyez sur **Entrée**
4. Attendez 3 à 10 secondes (le LLM génère le SQL)
5. La réponse apparaît avec :
   - Un texte explicatif
   - Un tableau de données (cliquez sur "📊 Voir les données brutes")
   - Un graphique si pertinent

### Activer l'affichage du SQL

Dans la sidebar gauche, activez **"🔍 Afficher le SQL généré"**
pour voir la requête SQL exécutée sous chaque réponse.
Utile pour vérifier ce que l'application a compris.

### Questions suggérées pour tester
```
# Statistiques générales
Combien de sièges chaque parti a-t-il obtenus ?
Quel est le taux de participation national moyen ?
Combien de femmes ont été élues ?

# Rankings
Top 5 des candidats avec le plus de voix
Quelles sont les 3 circonscriptions avec le plus fort taux de participation ?
Les 10 plus faibles scores parmi les élus

# Graphiques (ajoutez "graphique" ou "histogramme")
Fais un graphique de la répartition des sièges par parti
Histogramme du nombre d'élus par région
Camembert des partis présents à l'Assemblée

# Questions spécifiques
Qui a gagné dans AGBOVILLE COMMUNE ?
Quels candidats PDCI-RDA ont été élus dans la région BELIER ?
Quel est le score de DIMBA N'GOU PIERRE ?

# Hors périmètre (pour tester les guardrails)
Quel temps faisait-il le jour de l'élection ?
→ L'application doit répondre que cette info n'est pas dans le dataset
```

---

## Structure du projet
```
edan-chat/
│
├── 📁 data/                          ← Données (créé automatiquement)
│   ├── EDAN_2025_RESULTAT_...pdf     ← PDF source (à placer manuellement)
│   ├── elections.duckdb              ← Base de données (créée par make ingest)
│   └── elections.csv                 ← Export CSV de secours
│
├── 📁 ingestion/                     ← Pipeline ETL
│   ├── extract.py                    ← Lit le PDF → lignes brutes
│   ├── transform.py                  ← Nettoie et normalise
│   └── load.py                       ← Charge dans DuckDB
│
├── 📁 agent/                         ← Intelligence de l'application
│   ├── sql_agent.py                  ← Envoie la question à GPT-4o → SQL → réponse
│   ├── guardrails.py                 ← Sécurité : bloque les requêtes dangereuses
│   └── chart_gen.py                  ← Génère les graphiques Plotly
│
├── 📁 app/                           ← Interface utilisateur
│   ├── app.py                        ← Interface Streamlit (le chat)
│   └── config.py                     ← Configuration centrale (chemins, clés, limites)
│
├── 📁 tests/                         ← Tests automatisés
│   ├── test_ingestion.py             ← Tests du pipeline ETL
│   └── test_agent.py                 ← Tests de l'agent + guardrails
│
├── .env                              ← Votre clé API (à ne jamais commiter sur Git)
├── .env.example                      ← Modèle de configuration
├── .gitignore                        ← Fichiers à exclure de Git
├── requirements.txt                  ← Dépendances Python
├── Makefile                          ← Commandes raccourcies
└── README.md                         ← Ce fichier
```

---

## Résolution de problèmes

### ❌ `ModuleNotFoundError: No module named 'openai'`

Vous n'avez pas installé les dépendances ou l'environnement virtuel
n'est pas activé.
```bash
# Réactiver l'environnement virtuel
source venv/bin/activate    # Mac/Linux
venv\Scripts\activate       # Windows

# Réinstaller
pip install -r requirements.txt
```

---

### ❌ `AuthenticationError: Invalid API key`

Votre clé OpenAI est incorrecte ou absente.

1. Vérifiez que le fichier `.env` existe à la racine du projet
2. Vérifiez que la clé commence par `sk-`
3. Vérifiez qu'il n'y a pas d'espace autour du `=`
```
# ✅ Correct
OPENAI_API_KEY=sk-proj-abc123...

# ❌ Incorrect (espace)
OPENAI_API_KEY = sk-proj-abc123...
```

---

### ❌ `FileNotFoundError: data/EDAN_2025_RESULTAT...pdf`

Le PDF n'est pas dans le bon dossier ou n'a pas le bon nom.
```bash
# Vérifier que le fichier existe
ls data/
# Doit afficher : EDAN_2025_RESULTAT_NATIONAL_DETAILS.pdf
```

---

### ❌ La base de données est vide / `Table election_results doesn't exist`

L'ingestion n'a pas été lancée. Relancez :
```bash
make ingest
```

---

### ❌ L'application répond "Une erreur est survenue"

1. Vérifiez que votre clé OpenAI a du crédit
   (allez sur [platform.openai.com/usage](https://platform.openai.com/usage))
2. Vérifiez votre connexion internet
3. Réessayez avec une question plus simple

---

### ❌ Les graphiques ne s'affichent pas

Actualisez la page (F5). Si le problème persiste, vérifiez que
`plotly` est bien installé :
```bash
pip install plotly --upgrade
```

---

### 💡 Astuce : réinitialiser complètement la base

Si les données semblent incorrectes :
```bash
# Supprimer la base et la recréer
rm data/elections.duckdb data/elections.csv
make ingest
```

---

## Décisions techniques

| Choix | Alternative | Raison |
|---|---|---|
| DuckDB | PostgreSQL / SQLite | Embarqué, rapide sur CSV/Parquet, parfait pour les démos locales |
| GPT-4o | Claude / Mistral | Excellent en Text-to-SQL, `response_format=json_object` garantit du JSON valide |
| Streamlit | Gradio / Flask | Minimal, déploiement en 1 ligne, natif avec pandas/plotly |
| pdfplumber | tabula / camelot | Meilleure gestion des tableaux multi-pages avec en-têtes répétées |

## Limitations connues

- L'extraction PDF est sensible à la qualité de la mise en page
  (certaines circonscriptions avec mise en page atypique peuvent être mal parsées)
- Le modèle GPT-4o peut générer un SQL incorrect pour des questions
  très ambiguës — les guardrails bloquent les requêtes dangereuses mais
  pas les requêtes logiquement incorrectes
- Les questions nécessitant une jointure complexe entre plusieurs
  circonscriptions peuvent donner des résultats inattendus

## Prochaines étapes (niveaux 2-4)

- **Niveau 2** : Ajout d'un routeur hybride SQL + RAG pour les questions
  floues (ex: "Tiapum" → "Tiapoum")
- **Niveau 3** : Agent avec clarification automatique des ambiguïtés
- **Niveau 4** : Observabilité (traces, métriques) et pipeline d'évaluation
