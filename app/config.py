import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
PDF_PATH = DATA_DIR / "EDAN_2025_RESULTAT_NATIONAL_DETAILS.pdf"
DB_PATH  = DATA_DIR / "elections.duckdb"
CSV_PATH = DATA_DIR / "elections.csv"

DATA_DIR.mkdir(exist_ok=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL      = "gpt-4o"

DB_TABLE_NAME          = "election_results"
SQL_MAX_ROWS           = 100
SQL_FORBIDDEN_KEYWORDS = [
    "DROP", "DELETE", "INSERT", "UPDATE", "ALTER",
    "CREATE", "TRUNCATE", "EXEC", "EXECUTE", "--", ";"
]

APP_TITLE = "Chat avec les resultats EDAN 2025"
APP_ICON  = "elections"
