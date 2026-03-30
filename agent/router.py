import re

SQL_KEYWORDS = [
    "combien", "nombre", "total", "count",
    "top", "classement", "liste",
    "taux", "taux de participation",
    "participation",
    "moyenne", "somme", "maximum", "minimum",
    "histogramme", "graphique", "camembert",
    "siege", "pourcentage", "rang",
    "plus", "moins", "comparer", "repartition",
    "par parti", "par region", "par candidat",
    "distribution", "gagnants par", "elus par",
    "par region",
    "qui a gagne", "qui a ete elu", "qui est elu",
    "vainqueur a", "gagnant a", "elu a",
    "a remporte", "a gagne", "qui a remporte",
    "sorti vainqueur",
    "resultats du", "resultats de", "resultats a",
    "scores du", "scores de",
    "montre les resultats", "montre-moi les resultats",
    "resultats dans",
    "top 10", "top 5", "top 3", "top 20",
    "les 10", "les 5", "les 3",
    "ete elu", "a ete elu", "qui a ete",
    "parler de", "victoire",
]

RAG_KEYWORDS = [
    "qui est", "qui sont",
    "comment", "pourquoi", "explique",
    "a propos", "information sur",
    "que sais-tu", "connais-tu",
    "sur quelle page", "quelle page",
    "numero de page", "dans quelle page",
    "ou se trouve", "trouve sur",
    "source", "page",
]

CHART_TRIGGERS = [
    "histogramme", "graphique", "camembert",
    "chart", "bar chart", "diagramme",
    "visualis", "courbe", "pie",
]

AGGREGATION_PATTERNS = [
    r"taux.{0,15}(par|dans|de|par)\s+(region|circonscription|parti)",
    r"participation.{0,15}(par|dans|de)\s+(region|circonscription)",
    r"(par|par)\s+region",
    r"moyenne.{0,20}region",
    r"top\s*\d+",
    r"combien.{0,30}(region|parti|candidat|siege)",
    r"repartition.{0,20}(region|parti)",
    r"(gagne|elu|remporte|vainqueur).{0,25}(a |dans |en )",
    r"qui.{0,15}(gagne|elu|remporte|vainqueur).{0,25}(a |dans |en |\?)",
    r"(resultat|score).{0,15}(a |dans |en )",
    r"sorti.{0,10}vainqueur",
    r"qui.{0,5}a.{0,5}(gagne|remporte|ete elu|ete|gagne)",
    r"(resultat|score).{0,10}(du|de la|des|d[eu])\s+\w+.{0,20}(a |dans |en )",
    r"(montre|liste|donne).{0,20}(resultat|score).{0,20}(du|de|des|d[eu])",
    r"(resultat|score).{0,5}(du|de|des|d[eu]).{0,20}(pdci|rhdp|fpi|independant)",
    r"taux.{0,20}(a |dans |en )\w",
    r"participation.{0,20}(a |dans |en )\w",
    r"top\s*\d+\s*(candidat|elu|gagnant|parti|region|voix|score)",
    r"\d+\s*(premier|meilleur|candidat).{0,20}(voix|score|siege)",
    r"(candidat|elu|gagnant).{0,20}(plus de voix|meilleur score)",
    r"qui\s+a\s+ete\s+elu",
    r"a\s+ete\s+elu",
    r"ete\s+elu",
    r"victoire.{0,20}(du|de|des|d[eu]|a |dans )",
    r"(parler|parle).{0,10}(de|du|de la|des).{0,30}(victoire|resultat|score)",
    r"qui\s+a\s+gagne",
    r"dans\s+la\s+region",
    r"region\s+du\s+\w+",
]

# Patterns qui forcent le routing vers RAG (questions de localisation PDF)
PAGE_PATTERNS = [
    r"(quelle|sur\s+quelle|numero\s+de)\s+page",
    r"ou\s+(se\s+trouve|trouver)",
    r"dans\s+quelle\s+page",
    r"(page|source).{0,20}(resultat|score|region|circo)",
    r"sur\s+quelle\s+page",
]


def _normalize_for_routing(text: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    sans = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[?!.,;:«»\"]", "", sans.lower()).strip()


def classify(question: str) -> str:
    q_norm = _normalize_for_routing(question)

    # ── AJOUT : court-circuit RAG pour les questions de localisation PDF ──
    for pattern in PAGE_PATTERNS:
        if re.search(pattern, q_norm):
            return "rag"

    for pattern in AGGREGATION_PATTERNS:
        if re.search(pattern, q_norm):
            return "sql"

    sql_score = sum(1 for kw in SQL_KEYWORDS if kw in q_norm)

    if any(t in q_norm for t in CHART_TRIGGERS):
        sql_score += 5

    rag_score = sum(1 for kw in RAG_KEYWORDS if kw in q_norm)

    words = q_norm.split()

    action_verbs = {"gagne", "remporte", "elu", "vainqueur", "obtenu", "score", "ete"}
    starts_with_qui = words and words[0] == "qui"
    has_action = any(v in q_norm for v in action_verbs)

    if starts_with_qui and not has_action:
        rag_score += 2

    content_words = [w for w in words if len(w) >= 4]
    if len(content_words) <= 2:
        rag_score += 1

    if sql_score > rag_score:
        return "sql"
    elif rag_score >= 1:
        return "rag"
    else:
        return "sql"


def should_apply_fuzzy(question: str) -> bool:
    import unicodedata

    def norm(t):
        nfkd = unicodedata.normalize("NFKD", t)
        return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()

    q_clean = re.sub(r"[?!.,;:«»\"]", "", question).strip()

    analytical_only = re.compile(
        r"^(combien|taux|participation|top\s*\d|histogramme|"
        r"classement|repartition|nombre|total|moyenne|"
        r"siege|graphique|camembert)",
        re.IGNORECASE
    )
    if analytical_only.match(q_clean):
        return False

    hard_stops = {
        "la", "le", "les", "de", "du", "des", "un", "une",
        "en", "au", "aux", "et", "ou", "ni", "si", "car",
        "par", "sur", "sous", "dans", "avec", "sans", "pour",
        "pas", "non", "oui",
        "je", "tu", "il", "elle", "nous", "vous", "ils", "elles",
        "me", "te", "se", "lui", "leur", "moi", "toi", "soi",
        "mon", "ton", "son", "mes", "tes", "ses",
        "peux", "peut", "puis", "pouvez", "voulez", "veux",
        "est", "sont", "ont", "avez", "avons", "avoir", "etre",
        "dit", "dis", "fait", "sait", "voit", "veut",
        "dire", "faire", "savoir", "voir", "vouloir",
        "parler", "parle", "montrer", "montre", "donner", "donne",
        "expliquer", "explique", "raconter", "raconte",
        "qui", "que", "quoi", "dont", "comment", "pourquoi",
        "quand", "combien", "quel", "quelle", "quels", "quelles",
        "bien", "mal", "tres", "peu", "trop", "plus", "moins",
        "tout", "tous", "rien", "aussi", "encore", "deja",
        "stp", "svp", "merci", "bonjour", "salut",
        "region", "victoire", "defaite", "vainqueur", "gagnant",
        "resultat", "score", "taux", "siege", "parti", "candidat",
        "election", "vote", "voix", "elu", "elue", "elus",
        "info", "source", "page",
        "peux", "parler", "ete", "obtenus", "remporte", "gagne",
        "aide", "aider", "liste", "indique", "affiche",
        "tau", "partcipation", "resulats", "simona", "simon",
        # AJOUT connecteurs
        "abord", "dabord", "ensuite", "puis", "enfin",
        "premierement", "suite",
    }

    words = q_clean.split()

    return any(
        len(norm(w)) >= 5
        and norm(w) not in hard_stops
        for w in words
    )