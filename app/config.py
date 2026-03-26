import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Chemins ───────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
PDF_PATH = DATA_DIR / "EDAN_2025_RESULTAT_NATIONAL_DETAILS.pdf"
DB_PATH  = DATA_DIR / "elections.duckdb"
CSV_PATH = DATA_DIR / "elections.csv"
DATA_DIR.mkdir(exist_ok=True)

# ── LLM ───────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    import warnings
    warnings.warn(
        "OPENAI_API_KEY est vide. "
        "Créez un fichier .env avec OPENAI_API_KEY=sk-... avant de lancer l'app.",
        stacklevel=2,
    )

LLM_MODEL = "gpt-4o"

# ── Base de données ───────────────────────────────────────────────
DB_TABLE_NAME = "election_results"
SQL_MAX_ROWS  = 100

# ── Guardrails SQL ────────────────────────────────────────────────
# Source unique : guardrails.py importe depuis ici
# (supprime la duplication signalée dans la review)
SQL_FORBIDDEN_KEYWORDS = [
    "DROP", "DELETE", "INSERT", "UPDATE", "ALTER",
    "CREATE", "TRUNCATE", "EXEC", "EXECUTE",
]

ALLOWED_TABLES = {
    "election_results",
    "vw_winners",
    "vw_turnout",
    "vw_results_clean",
}

# ── App ───────────────────────────────────────────────────────────
APP_TITLE = "Chat avec les résultats EDAN 2025"
APP_ICON  = "🗳️"