import duckdb
import pandas as pd
from pathlib import Path
from app.config import DB_PATH, DB_TABLE_NAME, CSV_PATH


def get_connection():
    return duckdb.connect(str(DB_PATH))


def create_schema(conn):
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_TABLE_NAME} (
            id                  INTEGER,
            page                INTEGER,
            region              VARCHAR,
            circonscription     VARCHAR,
            nb_bv               INTEGER,
            inscrits            BIGINT,
            votants             BIGINT,
            taux_participation  DOUBLE,
            suffrages_exprimes  BIGINT,
            bulletins_blancs    BIGINT,
            bulletins_nuls      BIGINT,
            parti               VARCHAR,
            candidat            VARCHAR,
            score               BIGINT,
            pct_score           DOUBLE,
            elu                 BOOLEAN,
            search_circo        VARCHAR
        )
    """)

    conn.execute(f"""
        CREATE OR REPLACE VIEW vw_winners AS
        SELECT region, circonscription, parti, candidat, score, pct_score
        FROM {DB_TABLE_NAME}
        WHERE elu = TRUE
        ORDER BY region, circonscription
    """)

    conn.execute(f"""
        CREATE OR REPLACE VIEW vw_turnout AS
        SELECT
            region,
            ROUND(AVG(taux_participation), 2) AS avg_taux_participation,
            SUM(inscrits)                     AS total_inscrits,
            SUM(votants)                      AS total_votants,
            COUNT(DISTINCT circonscription)   AS nb_circonscriptions
        FROM {DB_TABLE_NAME}
        WHERE taux_participation IS NOT NULL
        GROUP BY region
        ORDER BY avg_taux_participation DESC
    """)

    conn.execute(f"""
        CREATE OR REPLACE VIEW vw_results_clean AS
        SELECT id, region, circonscription, parti, candidat,
               score, pct_score, elu,
               inscrits, votants, taux_participation, suffrages_exprimes
        FROM {DB_TABLE_NAME}
    """)


def load_dataframe(df, conn):
    conn.execute(f"DELETE FROM {DB_TABLE_NAME}")

    df = df.copy()
    df.insert(0, "id", range(1, len(df) + 1))

    # Forcer les types numeriques en int64 pour eviter overflow
    for col in ["inscrits", "votants", "suffrages_exprimes",
                "bulletins_blancs", "bulletins_nuls", "score", "nb_bv"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")

    df["elu"] = df["elu"].fillna(False).astype(bool)
    df["taux_participation"] = pd.to_numeric(
        df["taux_participation"], errors="coerce"
    ).astype("float64")
    df["pct_score"] = pd.to_numeric(
        df["pct_score"], errors="coerce"
    ).astype("float64")

    conn.execute(f"INSERT INTO {DB_TABLE_NAME} SELECT * FROM df")
    df.to_csv(CSV_PATH, index=False)

    count = conn.execute(
        f"SELECT COUNT(*) FROM {DB_TABLE_NAME}"
    ).fetchone()[0]
    return count


def run_ingestion_pipeline(pdf_path):
    from ingestion.extract import extract_raw_tables
    from ingestion.transform import transform

    print("Extraction du PDF...")
    raw_rows = extract_raw_tables(pdf_path)
    print(f"   -> {len(raw_rows)} lignes brutes extraites")

    print("Transformation et nettoyage...")
    df = transform(raw_rows)
    print(f"   -> {len(df)} lignes apres nettoyage")

    print("Chargement en base DuckDB...")
    conn = get_connection()

    # Supprimer ancienne base si schema incompatible
    try:
        create_schema(conn)
    except Exception:
        conn.close()
        import os
        os.remove(str(DB_PATH))
        conn = get_connection()
        create_schema(conn)

    count = load_dataframe(df, conn)
    conn.close()
    print(f"   OK : {count} lignes en base")
    return count
