import re
import unicodedata


def _strip_accents(text: str) -> str:
    """Supprime les accents pour la comparaison de patterns."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# Patterns SQL destructifs ou d'exfiltration
BLOCKED_PATTERNS = [
    (r"\bDROP\b",      "DROP"),
    (r"\bDELETE\b",    "DELETE"),
    (r"\bINSERT\b",    "INSERT"),
    (r"\bUPDATE\b",    "UPDATE"),
    (r"\bALTER\b",     "ALTER"),
    (r"\bCREATE\b",    "CREATE"),
    (r"\bTRUNCATE\b",  "TRUNCATE"),
    (r"\bEXEC\b",      "EXEC"),
    (r"\bEXECUTE\b",   "EXECUTE"),
    (r"\bUNION\b",     "UNION"),          # exfiltration via UNION
    (r"\bINTO\b",      "INTO"),           # SELECT INTO
    (r"\bOUTFILE\b",   "OUTFILE"),        # MySQL dump
    (r"--",            "commentaire --"), # injection via commentaire
    (r"/\*",           "commentaire /*"), # injection bloc
    (r";\s*\w",        "multi-statement"), # chaînage de requêtes
]

# Tables et vues autorisées
ALLOWED_TABLES = {
    "election_results",
    "vw_winners",
    "vw_turnout",
    "vw_results_clean",
}

# Limite de lignes maximale
DEFAULT_LIMIT = 100


class SQLValidationError(Exception):
    pass


def validate_sql(sql: str) -> str:
    """
    Valide et sécurise une requête SQL générée par le LLM.

    Vérifications :
    1. Doit commencer par SELECT
    2. Aucun mot-clé destructif ou d'exfiltration
    3. Doit référencer uniquement les tables/vues autorisées
    4. Injection automatique de LIMIT si absent

    Returns:
        La requête SQL sécurisée (avec LIMIT garanti)

    Raises:
        SQLValidationError si la requête est dangereuse
    """
    if not sql or not sql.strip():
        raise SQLValidationError("La requête SQL générée est vide.")

    sql_stripped = sql.strip()

    # Règle 1 : uniquement SELECT
    if not re.match(r"^\s*SELECT\b", sql_stripped, re.IGNORECASE):
        raise SQLValidationError(
            f"Seules les requêtes SELECT sont autorisées. "
            f"Reçu : '{sql_stripped[:40]}...'"
        )

    # Règle 2 : aucun mot-clé dangereux
    for pattern, label in BLOCKED_PATTERNS:
        if re.search(pattern, sql_stripped, re.IGNORECASE):
            raise SQLValidationError(
                f"Instruction non autorisée détectée : {label}. "
                f"Requête refusée pour des raisons de sécurité."
            )

    # Règle 3 : vérification des tables référencées
    # Extraction des noms de tables (FROM, JOIN)
    table_refs = re.findall(
        r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        sql_stripped,
        re.IGNORECASE,
    )
    for table in table_refs:
        if table.lower() not in ALLOWED_TABLES:
            raise SQLValidationError(
                f"Table non autorisée : '{table}'. "
                f"Tables disponibles : {', '.join(sorted(ALLOWED_TABLES))}"
            )

    # Règle 4 : injection de LIMIT si absent
    if not re.search(r"\bLIMIT\b", sql_stripped, re.IGNORECASE):
        sql_stripped = sql_stripped.rstrip(";") + f" LIMIT {DEFAULT_LIMIT}"

    return sql_stripped


def explain_refusal(question: str) -> str:
    """
    Génère un message clair pour les questions hors périmètre.
    """
    q_preview = question[:80] + ("..." if len(question) > 80 else "")
    return (
        f"Cette question n'est pas disponible dans le dataset électoral EDAN 2025.\n\n"
        f"**Ce qui a été cherché :** résultats liés à « {q_preview} »\n\n"
        f"**Le dataset contient :** régions, circonscriptions, candidats, partis, "
        f"scores, taux de participation et résultats des élections législatives "
        f"ivoiriennes du 27 décembre 2025.\n\n"
        f"**Suggestions :**\n"
        f"- Mentionnez un nom de région (ex: PORO, GBEKE, DISTRICT AUTONOME D ABIDJAN)\n"
        f"- Mentionnez un parti (ex: RHDP, PDCI-RDA, INDEPENDANT)\n"
        f"- Posez une question sur les résultats, les scores ou le taux de participation"
    )


def is_adversarial_prompt(user_input: str) -> bool:
    """
    Détecte les tentatives de prompt injection ou de manipulation.
    Retourne True si la question semble malveillante.
    """
    adversarial_patterns = [
        r"ignore\s+(tes|vos|les|toutes\s+les)\s+(instructions|regles|regles)",
        r"ignore\s+your\s+rules",
        r"system\s+prompt",
        r"api.{0,10}key",
        r"DROP\s+TABLE",
        r"exfiltrat",
        r"sans\s+limit",
        r"toutes?\s+les?\s+lignes?\s+sans",
        r"montre.{0,20}base.{0,20}entiere",
        r"show.{0,20}entire.{0,20}database",
    ]
    user_lower = _strip_accents(user_input.lower())
    for pattern in adversarial_patterns:
        if re.search(pattern, user_lower, re.IGNORECASE):
            return True
    return False


def get_adversarial_response() -> dict:
    """
    Réponse standardisée pour les prompts adversariaux.
    """
    return {
        "text": (
            "Cette demande a été refusée car elle semble tenter de contourner "
            "les règles de sécurité du système.\n\n"
            "Je suis configuré pour répondre uniquement aux questions portant "
            "sur les résultats électoraux EDAN 2025, en lecture seule.\n\n"
            "Les opérations suivantes sont interdites : modification de la base, "
            "accès à d'autres tables, contournement des limites de résultats, "
            "exposition de la configuration système."
        ),
        "dataframe":  None,
        "sql":        None,
        "chart_type": "none",
        "error":      "adversarial_prompt_detected",
        "route":      "refused",
    }