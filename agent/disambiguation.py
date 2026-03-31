"""
Détection déterministe d'ambiguïtés géographiques par requête DB.
Appelée AVANT le LLM dans sql_agent.answer() — zéro coût en tokens.

L'UI de clarification (boutons) dans app/app.py est déjà complète ;
elle attend result["ambiguous"] = True et result["ambiguity_options"] = [list].
"""
from __future__ import annotations

import re

from agent.fuzzy import normalize, NEVER_CORRECT, STOP_WORDS

# Au-delà de ce seuil → requête large (ex: Abidjan = 20+ circos),
# laisser le LLM gérer en retournant tous les résultats.
MAX_AMBIG_OPTIONS = 8

# Longueur minimale d'un terme géographique candidat
MIN_TERM_LENGTH = 4


def _extract_geo_terms(question: str) -> list[str]:
    """
    Extrait les termes géographiques candidats (1-2 mots, non stop-words).
    Retourne une liste ordonnée du plus long au plus court pour privilegier
    les bigrams ("grand bassam") avant les unigrammes ("bassam").
    """
    q_clean = re.sub(r"[?!.,;:«»\"']", "", question).strip()
    q_norm = normalize(q_clean)
    words = q_norm.split()

    terms: list[str] = []

    # 1-mot
    for w in words:
        if (
            len(w) >= MIN_TERM_LENGTH
            and w not in NEVER_CORRECT
            and w not in STOP_WORDS
        ):
            terms.append(w)

    # 2-mots (ex: "grand bassam", "san pedro", "grand lahou")
    for i in range(len(words) - 1):
        bigram = f"{words[i]} {words[i + 1]}"
        if (
            len(bigram) >= MIN_TERM_LENGTH + 2
            and words[i] not in NEVER_CORRECT
            and words[i + 1] not in NEVER_CORRECT
        ):
            terms.append(bigram)

    # Dédupliquer en conservant les plus longs en premier
    seen: set[str] = set()
    result: list[str] = []
    for t in sorted(terms, key=len, reverse=True):
        if t not in seen:
            seen.add(t)
            result.append(t)

    return result[:6]  # cap pour éviter des requêtes DB excessives


def _query_matching_circos(term: str, conn) -> list[str]:
    """
    Retourne les circonscriptions distinctes contenant `term` (ILIKE).
    Limité à MAX_AMBIG_OPTIONS + 1 pour détecter le cas "> seuil" efficacement.
    """
    rows = conn.execute(
        """
        SELECT DISTINCT circonscription
        FROM election_results
        WHERE circonscription ILIKE ?
        LIMIT ?
        """,
        [f"%{term}%", MAX_AMBIG_OPTIONS + 1],
    ).fetchall()
    return [r[0] for r in rows if r[0]]


def detect_ambiguity(question: str, conn) -> dict | None:
    """
    Retourne un dict d'ambiguïté si 2 à MAX_AMBIG_OPTIONS circonscriptions
    matchent un terme géographique de la question, None sinon.

    Forme du dict retourné (compatible avec l'UI de app/app.py) :
    {
        "term":     "bouake",
        "options":  ["BOUAKE, VILLE", "..., BOUAKE, SOUS-PREFECTURE"],
        "question": "Plusieurs circonscriptions correspondent à « bouake ».\n..."
    }

    Exemples :
    - "Résultats à Bouaké" → 2 circos → ambiguïté déclenchée
    - "Qui a gagné à Abidjan ?" → 20+ circos → skippé (LLM gère)
    - "Qui a gagné à Tiapoum ?" → 1 circo → None
    - "Combien de sièges ?" → aucun terme géo → None
    """
    terms = _extract_geo_terms(question)

    for term in terms:
        matches = _query_matching_circos(term, conn)

        # Trop de résultats = requête région large → laisser le LLM
        if len(matches) > MAX_AMBIG_OPTIONS:
            continue

        if len(matches) >= 2:
            return {
                "term": term,
                "options": matches,
                "question": (
                    f"Plusieurs circonscriptions correspondent à « {term} ».\n"
                    f"Précisez laquelle vous souhaitez :"
                ),
            }

    return None
