import re
import unicodedata
import pandas as pd


PARTY_ALIASES = {
    "RHDP CI":    "RHDP",
    "R.H.D.P":    "RHDP",
    "PDCI RDA":   "PDCI-RDA",
    "PDCI":       "PDCI-RDA",
    "INDEPENDANTE": "INDEPENDANT",
}


def clean_number(value):
    """'27,00%' -> 27.0 | '1 234' -> 1234.0 | None -> None"""
    if value is None or (isinstance(value, float) and str(value) == "nan"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("%", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def normalize_party(name):
    """Normalise le nom du parti. Ex: 'R.H.D.P' -> 'RHDP'"""
    if not name:
        return name
    clean = re.sub(r'\s+', ' ', name.strip().upper().replace(".", ""))
    return PARTY_ALIASES.get(clean, name.strip().upper())


def normalize_text(text):
    """Retire les accents et met en minuscules pour la recherche fuzzy."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_text.lower().strip()


def transform(raw_rows):
    """
    Nettoie et normalise les lignes brutes extraites du PDF.
    Retourne un DataFrame pandas propre.
    """
    if not raw_rows:
        return pd.DataFrame()

    df = pd.DataFrame(raw_rows)

    # Conversion numerique
    for col in ["inscrits", "votants", "suffrages_exprimes",
                "bulletins_blancs", "bulletins_nuls", "score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "taux_participation" in df.columns:
        df["taux_participation"] = df["taux_participation"].apply(clean_number)

    if "pct_score" in df.columns:
        df["pct_score"] = df["pct_score"].apply(clean_number)

    # Normalisation texte
    if "parti" in df.columns:
        df["parti"] = df["parti"].apply(normalize_party)

    if "circonscription" in df.columns:
        df["search_circo"] = df["circonscription"].apply(normalize_text)

    # Types
    df["elu"] = df["elu"].fillna(False).astype(bool)

    # Filtrer lignes invalides
    df = df.dropna(subset=["candidat", "score"])
    df = df[df["candidat"].str.len() > 2]
    df = df[df["score"] > 0]
    df = df.reset_index(drop=True)

    return df
