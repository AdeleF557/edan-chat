import json
import pandas as pd
from openai import OpenAI
from app.config import OPENAI_API_KEY, LLM_MODEL, SQL_MAX_ROWS
from agent.guardrails import (
    validate_sql, SQLValidationError, explain_refusal,
    is_adversarial_prompt, get_adversarial_response,
)
from agent.router import classify, should_apply_fuzzy
from agent.fuzzy import extract_and_correct_entities
from agent.rag import answer_with_rag
from ingestion.load import get_connection

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


SYSTEM_PROMPT = """
Tu es un assistant analytique specialise dans les resultats electoraux ivoiriens.
Tu reponds UNIQUEMENT a partir du dataset des elections legislatives du 27 decembre 2025.

IMPORTANT : Les noms de lieux et de personnes dans les questions ont deja ete corriges
par un systeme de fuzzy matching. Traite-les comme corrects meme s ils semblent inhabituels.

Schema de la base de donnees :

Table principale : election_results
  - id                 INTEGER
  - page               INTEGER  : numero de page dans le PDF source (TOUJOURS inclure pour citations)
  - region             VARCHAR
  - circonscription    VARCHAR
  - nb_bv              INTEGER
  - inscrits           BIGINT
  - votants            BIGINT
  - taux_participation DOUBLE
  - suffrages_exprimes BIGINT
  - bulletins_blancs   BIGINT
  - bulletins_nuls     BIGINT
  - parti              VARCHAR
  - candidat           VARCHAR
  - score              BIGINT
  - pct_score          DOUBLE
  - elu                BOOLEAN

Vues disponibles :
  - vw_winners : elus uniquement
    COLONNES : region, circonscription, parti, candidat, score, pct_score, page
    Exemple : SELECT region, circonscription, parti, candidat, score, pct_score, page
              FROM vw_winners WHERE region ILIKE '%poro%' LIMIT 100

  - vw_turnout : participation par region
    COLONNES : region, avg_taux_participation, total_inscrits, total_votants, nb_circonscriptions
    ATTENTION : PAS de colonne page ni circonscription dans cette vue.

  - vw_results_clean : tous les candidats individuels
    COLONNES : region, circonscription, parti, candidat, score, pct_score, elu, inscrits, votants, taux_participation, page

REGLES SQL STRICTES :
1. SELECT uniquement, LIMIT 100 maximum.
2. TOUJOURS inclure la colonne 'page' quand la vue la possede (vw_winners, vw_results_clean).
3. Pour top N candidats par voix :
   SELECT region, circonscription, parti, candidat, score, pct_score, page
   FROM vw_results_clean ORDER BY score DESC LIMIT N
4. Pour les elus d une region :
   SELECT region, circonscription, parti, candidat, score, pct_score, page
   FROM vw_winners WHERE region ILIKE '%nom_region%' LIMIT 100
5. Pour les elus dans une circonscription :
   SELECT region, circonscription, parti, candidat, score, pct_score, page
   FROM vw_winners WHERE circonscription ILIKE '%nom_ville%' LIMIT 100
6. Pour compter les sieges :
   SELECT COUNT(*) as nb_sieges FROM vw_winners WHERE parti ILIKE '%RHDP%'
7. Pour taux de participation par region :
   SELECT * FROM vw_turnout ORDER BY avg_taux_participation DESC LIMIT 100
8. Utilise ILIKE pour les recherches (insensible a la casse).
9. Pour "Abidjan" : WHERE region ILIKE '%abidjan%'
10. out_of_scope UNIQUEMENT pour meteo, sport, actualite non-electorale.

EXEMPLES CRITIQUES :
- "Top 10 candidats avec le plus de voix" ->
  SELECT region, circonscription, parti, candidat, score, pct_score, page
  FROM vw_results_clean ORDER BY score DESC LIMIT 10

- "Qui a gagne dans la region du Poro" ->
  SELECT region, circonscription, parti, candidat, score, pct_score, page
  FROM vw_winners WHERE region ILIKE '%poro%' LIMIT 100

- "Elus a Korhogo" ->
  SELECT region, circonscription, parti, candidat, score, pct_score, page
  FROM vw_winners WHERE circonscription ILIKE '%korhogo%' LIMIT 100

- "Resultats du PDCI a Agboville" ->
  SELECT region, circonscription, parti, candidat, score, pct_score, page
  FROM vw_results_clean
  WHERE parti ILIKE '%pdci%' AND circonscription ILIKE '%agboville%'
  LIMIT 100

DETECTION D AMBIGUITE :
Si un lieu correspond a plusieurs circonscriptions, retourne-les toutes et
mets ambiguous=true avec une note dans ambiguity_note.

MEMOIRE DE CONVERSATION :
Utilise l historique pour resoudre les references implicites.
- "et pour le PDCI ?" → meme region/circo que precedemment, filtre sur parti PDCI-RDA
- "dans cette region ?" → utilise la region du contexte de session
- "et lui ?" / "et pour eux ?" → utilise le dernier_parti du contexte
- Si "dernier_parti" est dans le contexte et la question mentionne un autre parti, utilise ce nouveau parti

Reponds en JSON strict :
{
  "intent": "aggregation|ranking|chart|factual|out_of_scope",
  "sql": "SELECT ...",
  "explanation": "explication courte en francais",
  "chart_type": "bar|pie|none",
  "ambiguous": false,
  "ambiguity_note": ""
}
"""

AGGREGATION_HINTS = [
    "taux", "participation", "moyenne", "total", "combien",
    "classement", "top ", "siege", "elu", "gagnant", "vainqueur",
    "remporte", "gagne", "score",
]


def _needs_sql_aggregation(question: str) -> bool:
    return any(hint in question.lower() for hint in AGGREGATION_HINTS)


def _build_messages(
    question: str,
    history: list | None = None,
    session_context: dict | None = None,
) -> list:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if session_context:
        ctx_lines = ["CONTEXTE DE SESSION (entités confirmées par l'utilisateur) :"]
        for k, v in session_context.items():
            ctx_lines.append(f"  - {k} = {v}")
        ctx_lines.append("")
        ctx_lines.append("RÈGLES DE RÉSOLUTION DES RÉFÉRENCES IMPLICITES :")
        ctx_lines.append("  - 'et pour le PDCI ?' → même région/circo que précédemment, filtre parti PDCI-RDA")
        ctx_lines.append("  - 'et pour le RHDP ?' → même région/circo, filtre parti RHDP")
        ctx_lines.append("  - 'dans cette région ?' → utilise la region du contexte")
        ctx_lines.append("  - 'et lui ?' / 'et pour eux ?' → utilise le dernier_parti du contexte")
        ctx_lines.append("  - Si 'dernier_parti' est défini, l'utiliser comme filtre par défaut")
        ctx_lines.append("Utilise ces valeurs pour résoudre les références implicites.")
        messages.append({"role": "system", "content": "\n".join(ctx_lines)})

    if history:
        for turn in history[-6:]:
            role    = turn.get("role", "")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": str(content)[:500]})

    messages.append({"role": "user", "content": question})
    return messages


def classify_and_generate_sql(
    question: str,
    history: list | None = None,
    session_context: dict | None = None,
) -> dict:
    messages = _build_messages(question, history, session_context)
    response = get_client().chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=1200,
    )
    return json.loads(response.choices[0].message.content.strip())


def execute_query(sql: str, conn) -> pd.DataFrame:
    return conn.execute(sql).df()


def _format_corrections(corrections: list) -> str:
    return "\n\n_Corrections orthographiques : " + ", ".join(
        f"**{c['original']}** → {c['matched']} (confiance : {c['score']:.0f}%)"
        for c in corrections
    ) + "_"


def answer(
    question: str,
    history: list | None = None,
    session_context: dict | None = None,
) -> dict:
    corrections       = []
    original_question = question

    # ── Étape 0 : détection prompt adversarial ──────────────────────────
    if is_adversarial_prompt(question):
        return get_adversarial_response()

    # ── Étape 1 : correction fuzzy ──────────────────────────────────────
    if should_apply_fuzzy(question):
        corrected_q, corrections = extract_and_correct_entities(question)
        if corrections:
            question = corrected_q

    # ── Étape 2 : routing ───────────────────────────────────────────────
    route = classify(question)

    if route == "rag" and _needs_sql_aggregation(question):
        route = "sql"

    # ── Étape 3a : chemin RAG ───────────────────────────────────────────
    if route == "rag":
        result = answer_with_rag(question)
        if corrections:
            result["text"] += _format_corrections(corrections)
        result["route"]             = "rag"
        result["ambiguous"]         = False
        result["ambiguity_options"] = []
        result["corrections"]       = corrections
        return result

    # ── Étape 3b : chemin SQL ───────────────────────────────────────────
    conn = get_connection(read_only=True)
    try:
        llm_output = classify_and_generate_sql(
            question,
            history=history,
            session_context=session_context,
        )
        intent = llm_output.get("intent", "factual")

        # Question hors périmètre
        if intent == "out_of_scope":
            rag_result = answer_with_rag(question)
            if rag_result.get("citations"):
                rag_result["route"]             = "rag_from_oos"
                rag_result["ambiguous"]         = False
                rag_result["ambiguity_options"] = []
                rag_result["corrections"]       = corrections
                return rag_result
            return {
                "text":              explain_refusal(original_question),
                "dataframe":         None,
                "sql":               None,
                "chart_type":        None,
                "error":             None,
                "route":             "refused",
                "ambiguous":         False,
                "ambiguity_options": [],
                "corrections":       corrections,
            }

        raw_sql = llm_output.get("sql", "")

        # Validation SQL (guardrails)
        try:
            safe_sql = validate_sql(raw_sql)
        except SQLValidationError as e:
            return {
                "text":              f"Requête refusée pour sécurité : {e}",
                "dataframe":         None,
                "sql":               raw_sql,
                "chart_type":        None,
                "error":             str(e),
                "route":             "sql_blocked",
                "ambiguous":         False,
                "ambiguity_options": [],
                "corrections":       corrections,
            }

        # Exécution
        try:
            df = execute_query(safe_sql, conn)
        except Exception as exec_err:
            rag_result          = answer_with_rag(original_question)
            rag_result["route"] = "rag_exec_fallback"
            rag_result["sql"]   = safe_sql
            rag_result["error"] = str(exec_err)
            rag_result.setdefault("ambiguous", False)
            rag_result.setdefault("ambiguity_options", [])
            rag_result["corrections"] = corrections
            if corrections:
                rag_result["text"] += _format_corrections(corrections)
            return rag_result

        # SQL retourne 0 résultats
        if df.empty:
            not_found_text = (
                f"Cette information n'est pas disponible dans le dataset.\n\n"
                f"J'ai cherché : **{question}**\n\n"
                f"_Vérifiez l'orthographe du lieu ou du parti, "
                f"ou reformulez votre question._"
            )
            if corrections:
                not_found_text += _format_corrections(corrections)
            return {
                "text":              not_found_text,
                "dataframe":         None,
                "sql":               safe_sql,
                "chart_type":        None,
                "error":             None,
                "route":             "sql_empty",
                "ambiguous":         False,
                "ambiguity_options": [],
                "corrections":       corrections,
            }

        text = llm_output.get("explanation", "")

        if len(df) == SQL_MAX_ROWS:
            text += f"\n\n_Résultats limités à {SQL_MAX_ROWS} lignes._"

        if corrections:
            text += _format_corrections(corrections)

        # Désambiguïsation (Level 3)
        is_ambiguous      = llm_output.get("ambiguous", False)
        ambiguity_note    = llm_output.get("ambiguity_note", "")
        ambiguity_options = []

        if is_ambiguous and ambiguity_note:
            text += f"\n\n⚠️ **Ambiguïté détectée :** {ambiguity_note}"
            if "circonscription" in df.columns and len(df) > 1:
                ambiguity_options = df["circonscription"].unique().tolist()

        return {
            "text":              text,
            "dataframe":         df,
            "sql":               safe_sql,
            "chart_type":        llm_output.get("chart_type", "none"),
            "error":             None,
            "route":             "sql",
            "ambiguous":         is_ambiguous,
            "ambiguity_options": ambiguity_options,
            "corrections":       corrections,
        }

    except Exception as e:
        return {
            "text":              f"Une erreur est survenue : {str(e)}",
            "dataframe":         None,
            "sql":               None,
            "chart_type":        None,
            "error":             str(e),
            "route":             "error",
            "ambiguous":         False,
            "ambiguity_options": [],
            "corrections":       corrections,
        }
    finally:
        conn.close()