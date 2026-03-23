import json
import re
import duckdb
import pandas as pd
from openai import OpenAI
from app.config import OPENAI_API_KEY, LLM_MODEL, DB_TABLE_NAME, SQL_MAX_ROWS
from agent.guardrails import validate_sql, SQLValidationError, explain_refusal
from ingestion.load import get_connection

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
Tu es un assistant analytique specialise dans les resultats electoraux ivoiriens.
Tu reponds UNIQUEMENT a partir du dataset des elections legislatives du 27 decembre 2025.

Schema de la base de donnees :

Table principale : election_results
  - region             VARCHAR  : nom de la region (ex: AGNEBY-TIASSA, GBEKE, PORO...)
  - circonscription    VARCHAR  : libelle complet de la circonscription
  - nb_bv              INTEGER  : nombre de bureaux de vote
  - inscrits           BIGINT   : nombre d electeurs inscrits
  - votants            BIGINT   : nombre d electeurs ayant vote
  - taux_participation DOUBLE   : taux de participation en pourcentage (ex: 27.0)
  - suffrages_exprimes BIGINT   : suffrages exprimes hors blancs et nuls
  - bulletins_blancs   BIGINT   : bulletins blancs
  - bulletins_nuls     BIGINT   : bulletins nuls
  - parti              VARCHAR  : parti politique (RHDP, PDCI-RDA, FPI, INDEPENDANT...)
  - candidat           VARCHAR  : nom complet du candidat en majuscules
  - score              BIGINT   : nombre de voix obtenues
  - pct_score          DOUBLE   : pourcentage des suffrages exprimes
  - elu                BOOLEAN  : TRUE si le candidat est elu(e)
  - search_circo       VARCHAR  : version normalisee pour recherche fuzzy

Vues disponibles :
  - vw_winners       : elus uniquement
    colonnes : region, circonscription, parti, candidat, score, pct_score
  - vw_turnout       : participation par region
    colonnes : region, avg_taux_participation, total_inscrits, total_votants, nb_circonscriptions
    IMPORTANT : cette vue n a PAS de colonne taux_participation, utiliser avg_taux_participation
  - vw_results_clean : resultats sans les listes electorales (slogans)
    colonnes identiques a election_results mais candidats individuels seulement

REGLES IMPORTANTES :
1. Genere SEULEMENT du SQL SELECT — jamais INSERT, UPDATE, DELETE, DROP.
2. Tout SQL doit inclure LIMIT 100.
3. Si la question nest pas liee aux elections, reponds avec intent = out_of_scope.
4. Pour le taux de participation par region : utiliser vw_turnout et avg_taux_participation.
5. Pour le top candidats par voix : utiliser vw_results_clean pour exclure les listes.
6. Toujours inclure region et circonscription dans les requetes sur les candidats.
7. Utilise ILIKE pour les recherches de noms (insensible a la casse).
8. Partis normalises : RHDP, PDCI-RDA, FPI, INDEPENDANT, LE BUFFLE, UNPR.

Reponds TOUJOURS en JSON valide :
{
  "intent": "aggregation|ranking|chart|factual|out_of_scope",
  "sql": "SELECT ...",
  "explanation": "explication courte en francais",
  "chart_type": "bar|pie|none"
}
"""


def classify_and_generate_sql(question):
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": question},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=800,
    )
    return json.loads(response.choices[0].message.content.strip())


def execute_query(sql, conn):
    return conn.execute(sql).df()


def format_dataframe_as_markdown(df, max_rows=20):
    if df.empty:
        return "_Aucun resultat trouve._"
    display_df = df.head(max_rows).copy()
    for col in display_df.select_dtypes(include=["float64"]).columns:
        display_df[col] = display_df[col].round(2)
    return display_df.to_markdown(index=False)


def answer(question):
    conn = get_connection()
    try:
        llm_output = classify_and_generate_sql(question)
        intent = llm_output.get("intent", "factual")

        if intent == "out_of_scope":
            return {
                "text": explain_refusal(question),
                "dataframe": None,
                "sql": None,
                "chart_type": None,
                "error": None,
            }

        raw_sql = llm_output.get("sql", "")

        try:
            safe_sql = validate_sql(raw_sql)
        except SQLValidationError as e:
            return {
                "text": f"Requete refusee : {e}",
                "dataframe": None,
                "sql": raw_sql,
                "chart_type": None,
                "error": str(e),
            }

        df = execute_query(safe_sql, conn)
        explanation = llm_output.get("explanation", "")
        table_md    = format_dataframe_as_markdown(df)
        text        = f"{explanation}\n\n{table_md}"

        if len(df) == SQL_MAX_ROWS:
            text += f"\n\n_Resultats limites a {SQL_MAX_ROWS} lignes._"

        return {
            "text": text,
            "dataframe": df,
            "sql": safe_sql,
            "chart_type": llm_output.get("chart_type", "none"),
            "error": None,
        }

    except Exception as e:
        return {
            "text": f"Une erreur est survenue : {str(e)}",
            "dataframe": None,
            "sql": None,
            "chart_type": None,
            "error": str(e),
        }
    finally:
        conn.close()
