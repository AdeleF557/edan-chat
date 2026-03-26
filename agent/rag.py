import chromadb
from chromadb.utils import embedding_functions
from ingestion.load import get_connection
from pathlib import Path

ROOT_DIR       = Path(__file__).parent.parent
CHROMA_DIR     = ROOT_DIR / "data" / "chroma"
COLLECTION_NAME = "election_results"

# FIX 4 : seuil de distance ChromaDB.
# ChromaDB retourne des distances cosinus [0, 2].
# En dessous de MAX_DISTANCE → résultat pertinent.
# Au-dessus → on ignore (source parasite).
# Calibré empiriquement : ~1.0 capture les vraies correspondances,
# > 1.2 sont généralement des faux positifs.
MAX_DISTANCE = 1.0


def get_embedding_function():
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="paraphrase-multilingual-MiniLM-L12-v2"
    )


def get_chroma_client():
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def search(query, n_results=8, max_distance=MAX_DISTANCE):
    """
    Recherche sémantique dans ChromaDB.

    FIX 4 : on demande plus de résultats (8 au lieu de 5) puis on filtre
    par distance → on garde seulement les chunks vraiment pertinents.
    Résultat : moins de sources parasites dans les citations.
    """
    client     = get_chroma_client()
    ef         = get_embedding_function()
    collection = client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
    )

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],  # FIX 4 : inclure distances
    )

    docs      = results["documents"][0]
    metas     = results["metadatas"][0]
    distances = results["distances"][0]  # FIX 4

    seen_keys = set()
    output    = []

    for doc, meta, dist in zip(docs, metas, distances):
        # FIX 4 : ignorer les chunks trop éloignés sémantiquement
        if dist > max_distance:
            continue

        key = (
            meta.get("page", "?"),
            meta.get("region", "?"),
            meta.get("circonscription", "?"),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)

        citation = (
            f"[Source : page {meta.get('page', '?')}, "
            f"{meta.get('region', '?')} - "
            f"{meta.get('circonscription', '?')}]"
        )
        output.append({
            "text":     doc,
            "metadata": meta,
            "citation": citation,
            "distance": dist,   # utile pour le debug
        })

    return output


def answer_with_rag(question, n_results=8):
    from openai import OpenAI
    from app.config import OPENAI_API_KEY, LLM_MODEL

    results = search(question, n_results)

    # FIX 3 (côté RAG) : message clair si aucun chunk pertinent trouvé
    # après filtrage par distance (≠ aucun chunk retourné du tout)
    if not results:
        return {
            "text": (
                "Cette information n'est pas disponible dans le dataset EDAN 2025.\n\n"
                "Vérifiez l'orthographe du nom de la région ou de la circonscription, "
                "ou reformulez votre question.\n\n"
                "_Conseil : utilisez le nom officiel, par exemple "
                "**DENGUELÉ** ou **FOLON** pour les régions du nord-ouest._"
            ),
            "dataframe":  None,
            "sql":        None,
            "chart_type": "none",
            "error":      None,
            "citations":  [],
        }

    context_parts = []
    for r in results:
        context_parts.append(f"{r['citation']}\n{r['text']}")
    context = "\n\n".join(context_parts)

    citations = list(dict.fromkeys(r["citation"] for r in results))

    client = OpenAI(api_key=OPENAI_API_KEY)

    system_prompt = """Tu es un assistant spécialisé dans les résultats électoraux ivoiriens (EDAN 2025).
RÈGLES STRICTES :
1. Réponds UNIQUEMENT à partir du contexte fourni ci-dessous.
2. Si l'information n'est pas dans le contexte, réponds EXACTEMENT :
   "Cette information n'est pas disponible dans le dataset."
   Puis explique brièvement ce que tu as cherché.
3. Ne fais AUCUNE supposition ou extrapolation.
4. Cite toujours la source (région, circonscription, page).
5. Sois concis et factuel.
6. Si la question demande un taux agrégé (par région, par parti...) et que le contexte
   ne contient que des valeurs partielles, liste les valeurs disponibles et précise
   qu'un calcul agrégé complet nécessiterait une requête SQL."""

    user_prompt = f"""Question : {question}

Contexte extrait du dataset (sources filtrées par pertinence) :
{context}

Réponds uniquement à partir de ce contexte."""

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0,
        max_tokens=600,
    )
    answer_text = response.choices[0].message.content

    if citations:
        citations_str = "\n".join(f"- {c}" for c in citations[:5])
        full_text = f"{answer_text}\n\n---\n**Sources :**\n{citations_str}"
    else:
        full_text = answer_text

    return {
        "text":       full_text,
        "dataframe":  None,
        "sql":        None,
        "chart_type": "none",
        "error":      None,
        "citations":  citations,  # exposé pour le fallback dans sql_agent.py
    }