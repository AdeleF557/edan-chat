import duckdb
import pandas as pd
from pathlib import Path
from app.config import DB_PATH, DB_TABLE_NAME, CSV_PATH


def get_connection(read_only: bool = False):
    return duckdb.connect(str(DB_PATH), read_only=read_only)


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

    # vw_winners — ajout de page pour les citations
    conn.execute(f"""
        CREATE OR REPLACE VIEW vw_winners AS
        SELECT region, circonscription, parti, candidat, score, pct_score, page
        FROM {DB_TABLE_NAME}
        WHERE elu = TRUE
        ORDER BY region, circonscription
    """)

    # vw_turnout — inchangée (agrégation par région, page non pertinente)
    conn.execute(f"""
        CREATE OR REPLACE VIEW vw_turnout AS
        WITH circo_stats AS (
            SELECT DISTINCT
                region, circonscription, taux_participation, inscrits, votants
            FROM {DB_TABLE_NAME}
            WHERE taux_participation IS NOT NULL
        )
        SELECT
            region,
            ROUND(AVG(taux_participation), 2) AS avg_taux_participation,
            SUM(inscrits)                     AS total_inscrits,
            SUM(votants)                      AS total_votants,
            COUNT(DISTINCT circonscription)   AS nb_circonscriptions
        FROM circo_stats
        GROUP BY region
        ORDER BY avg_taux_participation DESC
    """)

    # vw_results_clean — ajout de page pour les citations
    conn.execute(f"""
        CREATE OR REPLACE VIEW vw_results_clean AS
        SELECT
            region, circonscription, parti, candidat,
            score, pct_score, elu, inscrits, votants, taux_participation, page
        FROM {DB_TABLE_NAME}
        WHERE
            candidat IS NOT NULL
            AND LENGTH(TRIM(candidat)) > 5
            AND UPPER(candidat) NOT LIKE '%LISTE%'
            AND UPPER(candidat) NOT LIKE '%GROUPEMENT%'
            AND score > 0
        ORDER BY score DESC
    """)


def load_dataframe(df: pd.DataFrame, conn) -> int:
    df = df.copy()
    df.insert(0, "id", range(1, len(df) + 1))

    for col in [
        "inscrits", "votants", "suffrages_exprimes",
        "bulletins_blancs", "bulletins_nuls", "score", "nb_bv",
    ]:
        if col in df.columns:
            df[col] = (
                pd.to_numeric(df[col], errors="coerce")
                .fillna(0)
                .astype("int64")
            )

    df["elu"]                = df["elu"].fillna(False).astype(bool)
    df["taux_participation"] = pd.to_numeric(df["taux_participation"], errors="coerce").astype("float64")
    df["pct_score"]          = pd.to_numeric(df["pct_score"],          errors="coerce").astype("float64")

    conn.execute("BEGIN")
    try:
        conn.execute(f"DELETE FROM {DB_TABLE_NAME}")
        conn.execute(f"INSERT INTO {DB_TABLE_NAME} SELECT * FROM df")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    df.to_csv(CSV_PATH, index=False)
    return conn.execute(f"SELECT COUNT(*) FROM {DB_TABLE_NAME}").fetchone()[0]


def run_ingestion_pipeline(pdf_path):
    from ingestion.extract import extract_raw_tables
    from ingestion.transform import transform
    import os

    print("Extraction du PDF...")
    raw_rows = extract_raw_tables(pdf_path)
    print(f"  -> {len(raw_rows)} lignes brutes extraites")

    print("Transformation et nettoyage...")
    df = transform(raw_rows)
    print(f"  -> {len(df)} lignes après nettoyage")

    print("Chargement en base DuckDB...")
    conn = get_connection(read_only=False)

    try:
        create_schema(conn)
    except duckdb.CatalogException:
        print("  Schéma corrompu, réinitialisation de la base...")
        conn.close()
        os.remove(str(DB_PATH))
        conn = get_connection(read_only=False)
        create_schema(conn)

    try:
        count = load_dataframe(df, conn)
    finally:
        conn.close()

    print(f"  OK : {count} lignes en base")
    return count