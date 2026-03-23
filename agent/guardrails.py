import re
import sqlparse

DB_TABLE_NAME = "election_results"
SQL_MAX_ROWS  = 100

ALLOWED_TABLES = {
    "election_results",
    "vw_winners",
    "vw_turnout",
    "vw_results_clean",
}

SQL_FORBIDDEN_KEYWORDS = [
    "DROP", "DELETE", "INSERT", "UPDATE", "ALTER",
    "CREATE", "TRUNCATE", "EXEC", "EXECUTE",
]


class SQLValidationError(Exception):
    pass


def validate_sql(sql):
    if not sql or not sql.strip():
        raise SQLValidationError("La requete SQL est vide.")

    sql_clean = sql.strip()
    sql_clean = re.sub(r"--.*$", "", sql_clean, flags=re.MULTILINE)
    sql_clean = re.sub(r"/\*.*?\*/", "", sql_clean, flags=re.DOTALL)
    sql_clean = sql_clean.strip()

    parsed = sqlparse.parse(sql_clean)
    if not parsed:
        raise SQLValidationError("Impossible de parser la requete SQL.")

    stmt_type = parsed[0].get_type()
    if stmt_type != "SELECT":
        raise SQLValidationError(
            f"Seules les requetes SELECT sont autorisees. "
            f"Type detecte : {stmt_type or 'inconnu'}."
        )

    sql_upper = sql_clean.upper()
    for keyword in SQL_FORBIDDEN_KEYWORDS:
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, sql_upper):
            raise SQLValidationError(
                f"Mot-cle interdit detecte : {keyword}."
            )

    from_pattern = r"\bFROM\s+(\w+)|\bJOIN\s+(\w+)"
    tables_found = re.findall(from_pattern, sql_upper)
    tables_used  = {t for pair in tables_found for t in pair if t}
    unknown      = tables_used - {t.upper() for t in ALLOWED_TABLES}
    if unknown:
        raise SQLValidationError(
            f"Table(s) non autorisee(s) : {unknown}."
        )

    if "LIMIT" not in sql_upper:
        sql_clean = sql_clean.rstrip(";").rstrip()
        sql_clean = f"{sql_clean} LIMIT {SQL_MAX_ROWS}"

    return sql_clean


def explain_refusal(question):
    return (
        "Je ne peux pas repondre a cette demande car elle sort du perimetre "
        "du dataset EDAN 2025 ou tente une operation non autorisee.\n\n"
        "Je peux vous aider avec :\n"
        "- Les resultats par circonscription ou region\n"
        "- Les scores et classements des candidats\n"
        "- Les taux de participation\n"
        "- Les sieges obtenus par parti\n\n"
        "Essayez : *Combien de sieges le RHDP a-t-il obtenus ?*"
    )
