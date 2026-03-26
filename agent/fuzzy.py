import re
import unicodedata
from rapidfuzz import fuzz
from ingestion.load import get_connection


def load_stop_words():
    try:
        from nltk.corpus import stopwords
        nltk_words = set(stopwords.words("french"))
    except Exception:
        nltk_words = set()

    domain_words = {
        "combien", "comment", "pourquoi", "quand", "quel",
        "quelle", "quels", "quelles", "lequel", "laquelle",
        "gagne", "perdu", "elu", "vote", "obtenu", "remporte",
        "donne", "montre", "affiche", "calcule", "compte",
        "compare", "classe", "trie", "filtre", "cherche",
        "trouve", "indique", "explique", "parle", "dis",
        "liste", "donne", "montre",
        "siege", "sieges", "parti", "partis", "region", "regions",
        "candidat", "candidats", "taux", "participation",
        "vote", "votes", "voix", "score", "scores",
        "resultat", "resultats", "election", "elections",
        "depute", "deputes", "assemblee", "nationale",
        "commune", "communes", "sous", "prefecture", "prefectures",
        "liste", "listes", "top", "classement", "histogramme",
        "graphique", "camembert", "tableau", "nombre", "total",
        "temps", "fait", "faut", "peut", "doit",
        "plus", "moins", "fort", "faible", "meilleur", "pire",
        "qui", "quoi",
        "victoire", "defaite", "vainqueur", "gagnant",
        "sorti", "passe", "apres", "avant", "depuis",
        "tau", "taux", "partcipation", "participation",
        "simona", "score", "info", "information",
        "parler", "montre", "donnez",
        # AJOUTS
        "peux", "tu", "me", "nous", "vous",
        "ete", "elue", "obtenus", "stp", "svp",
        "merci", "bonjour", "salut", "aide", "aider",
        "parler", "remporte", "gagne",
    }

    return nltk_words | domain_words


STOP_WORDS = load_stop_words()

NEVER_CORRECT = {
    # Articles et prépositions courts
    "la", "le", "les", "de", "du", "des", "un", "une",
    "en", "au", "aux", "et", "ou", "ni", "si", "car",
    "par", "sur", "sous", "dans", "avec", "sans", "pour",
    "pas", "non", "oui", "est", "son", "ses", "mon", "mes",
    "ton", "tes", "lui", "ils", "eux", "elle", "elles",
    # Prépositions longues
    "dans", "pour", "avec", "entre", "vers", "chez",
    "depuis", "jusque", "avant", "apres",
    # Verbes courants
    "dit", "dis", "fait", "sait", "voit", "veut", "peut",
    "peux", "puis", "pouvez", "voulez", "veux",
    "dire", "etes", "sont", "avez", "avons",
    "parler", "montrer", "donner", "parle",
    # Pronoms
    "tu", "me", "nous", "vous", "ils", "elles", "je",
    # Mots de question
    "qui", "que", "quoi", "dont", "ou", "quel", "quelle",
    "quels", "quelles", "lequel", "laquelle",
    "comment", "pourquoi", "quand", "combien",
    # Adverbes
    "bien", "mal", "tres", "peu", "trop", "plus", "moins",
    "tout", "tous", "rien",
    # Mots du domaine non-entités
    "region", "victoire", "defaite", "vainqueur", "gagnant",
    "resultat", "score", "taux", "siege", "parti", "candidat",
    "stp", "montre", "donne", "liste", "indique",
    "parle", "raconte", "sorti", "passe",
    "simona", "simon", "info", "source", "page",
    "tau", "partcipation", "resulats",
    # Verbes/expressions conversationnelles
    "ete", "elue", "obtenus", "remporte", "gagne",
    "stp", "svp", "merci", "bonjour", "salut",
    "aide", "aider", "parler", "a",
}

PHONETIC_RULES = [
    (r"nne$", "n"),
    (r"nn",   "n"),
    (r"ss",   "s"),
    (r"ll",   "l"),
    (r"tt",   "t"),
    (r"-",    " "),
    (r"'",    " "),
]

_CACHE = None

THRESHOLDS = {
    "circonscription": 85,
    "region":          85,
    "parti":           87,
    "candidat":        93,
}

MIN_ENTITY_LENGTH = 5

WINDOW_SIZES = [1, 2, 3]


def normalize(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    sans_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sans_accents.lower().strip())


def phonetic_normalize(text: str) -> str:
    text = normalize(text)
    for pattern, replacement in PHONETIC_RULES:
        text = re.sub(pattern, replacement, text)
    return text


def get_all_entities(force_reload: bool = False) -> dict:
    global _CACHE
    if _CACHE and not force_reload:
        return _CACHE
    conn = get_connection()
    try:
        _CACHE = {
            "circonscription": [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT circonscription FROM election_results"
                ).fetchall() if r[0]
            ],
            "region": [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT region FROM election_results"
                ).fetchall() if r[0]
            ],
            "parti": [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT parti FROM election_results"
                ).fetchall() if r[0]
            ],
            "candidat": [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT candidat FROM election_results"
                ).fetchall() if r[0]
            ],
        }
        return _CACHE
    finally:
        conn.close()


def is_stop_phrase(phrase: str, window_size: int = 1) -> bool:
    phrase_norm = normalize(phrase)
    words = phrase_norm.split()

    if not words or len(phrase_norm) < MIN_ENTITY_LENGTH:
        return True

    if len(words) == 1 and words[0] in NEVER_CORRECT:
        return True

    first_word_stops = {
        "qui", "que", "quoi", "comment", "pourquoi", "quand",
        "combien", "quel", "quelle", "est", "sont", "ont",
        "gagne", "resultats", "donnez", "montre", "affiche",
        "donne", "liste", "top", "quels",
        "parle", "dis", "raconte", "explique",
        "victoire", "defaite",
        "peux", "pouvez", "puis", "voulez", "veux",
        "dans", "pour", "avec", "entre", "vers",
        "sur", "sous",
        "sorti", "sorite",
        "tau", "taux", "partcipation", "participation",
        "resulats", "resultat", "score", "quel", "quelle",
        "simona", "simon",
        "le", "la", "les", "du", "de", "des",
        # AJOUTS
        "tu", "me", "je", "nous", "vous", "a", "ete",
        "qui", "peux", "peut",
    }
    if words[0] in first_word_stops:
        return True

    if all(w in STOP_WORDS for w in words):
        return True

    if window_size >= 3:
        stop_count = sum(1 for w in words if w in STOP_WORDS or w in NEVER_CORRECT)
        if stop_count >= len(words) / 2:
            return True

    return False


def _is_plausible_entity(phrase_norm: str, window_size: int = 1) -> bool:
    words = phrase_norm.split()
    plausible_words = [
        w for w in words
        if len(w) >= 5 and w not in STOP_WORDS and w not in NEVER_CORRECT
    ]

    if window_size >= 3:
        return len(plausible_words) >= max(2, len(words) - 1)

    return len(plausible_words) >= 1


def multi_score(query_norm: str, candidate_norm: str) -> float:
    return max(
        fuzz.WRatio(query_norm, candidate_norm),
        fuzz.partial_ratio(query_norm, candidate_norm),
        fuzz.token_sort_ratio(query_norm, candidate_norm),
    )


def fuzzy_match(
    query: str,
    entity_type: str = None,
    threshold: float = None,
    window_size: int = 1,
) -> dict | None:
    if is_stop_phrase(query, window_size=window_size):
        return None

    query_clean = re.sub(r"[?!.,;:«»\"]", "", query).strip()
    if len(query_clean) < MIN_ENTITY_LENGTH:
        return None

    query_norm_check = normalize(query_clean)
    if not _is_plausible_entity(query_norm_check, window_size=window_size):
        return None

    entities = get_all_entities()
    types_to_search = (
        [(entity_type, entities.get(entity_type, []))]
        if entity_type
        else list(entities.items())
    )

    query_norm = normalize(query_clean)
    query_phon = phonetic_normalize(query_clean)
    best_match = None
    best_score = 0
    best_type  = None

    for etype, candidates in types_to_search:
        local_threshold = threshold if threshold is not None else THRESHOLDS.get(etype, 87)

        if window_size >= 3:
            local_threshold = max(local_threshold, 90)

        for candidate in candidates:
            cand_norm = normalize(candidate)
            cand_phon = phonetic_normalize(candidate)

            score = max(
                multi_score(query_norm, cand_norm),
                multi_score(query_phon, cand_phon),
            )

            if score > best_score and score >= local_threshold:
                best_score = score
                best_match = candidate
                best_type  = etype

    if best_match:
        return {
            "matched":     best_match,
            "score":       best_score,
            "entity_type": best_type,
            "original":    query,
        }
    return None


def extract_and_correct_entities(question: str) -> tuple[str, list]:
    words = question.split()
    corrections = []
    result_words = list(words)
    used = set()

    i = 0
    while i < len(words):
        if i in used:
            i += 1
            continue

        matched = False

        for window in WINDOW_SIZES:
            if i + window > len(words):
                continue

            phrase = " ".join(words[i:i + window])
            phrase_clean = re.sub(r"[?!.,;:«»\"]", "", phrase).strip()

            if len(normalize(phrase_clean)) < MIN_ENTITY_LENGTH:
                continue

            if is_stop_phrase(phrase_clean, window_size=window):
                continue

            result = fuzzy_match(phrase_clean, window_size=window)

            if result:
                if normalize(phrase_clean) == normalize(result["matched"]):
                    break

                corrections.append({
                    "original":    phrase_clean,
                    "matched":     result["matched"],
                    "score":       result["score"],
                    "entity_type": result["entity_type"],
                })
                result_words[i] = result["matched"]
                for j in range(i + 1, i + window):
                    result_words[j] = ""
                for j in range(i, i + window):
                    used.add(j)
                i += window
                matched = True
                break

        if not matched:
            i += 1

    final_words = [w for w in result_words if w != ""]
    return " ".join(final_words), corrections


def should_apply_fuzzy(question: str) -> bool:
    q_clean = re.sub(r"[?!.,;:«»\"]", "", question).strip()

    analytical_only = re.compile(
        r"^(combien|taux|participation|top\s+\d|histogramme|"
        r"classement|repartition|nombre|total|moyenne|"
        r"siege|graphique|camembert)",
        re.IGNORECASE
    )
    if analytical_only.match(q_clean):
        return False

    return any(
        len(w) >= 5
        and normalize(w) not in STOP_WORDS
        and normalize(w) not in NEVER_CORRECT
        for w in q_clean.split()
    )