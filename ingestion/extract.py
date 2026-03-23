import re
import pdfplumber
from pathlib import Path


# Mapping des regions ecrites verticalement -> nom complet
# Les lettres sont concatenees depuis la colonne 0 du tableau
# Dictionnaire de correspondance : texte brut extrait -> nom officiel
# Necessaire car les lettres verticales sont mal ordonnees par pdfplumber
REGION_MAP = {
    "AGNEB-YITASSA":               "AGNEBY-TIASSA",
    "ASSAIT-YBENGA":               "AGNEBY-TIASSA",
    "BAIFNG":                      "BAFING",
    "BEILER":                      "BELIER",
    "BOUNKAIN":                    "BOUNKANI",
    "GRANDSPONTS":                 "GRANDS PONTS",
    "GONTOUGO":                    "GONTOUGO",
    "GUEMON":                      "GUEMON",
    "HAU-TSASSANDRA":              "HAUT-SASSANDRA",
    "ARDNASSAS-TUAH":              "HAUT-SASSANDRA",
    "IDSTIRCTAUTONOME'DAIBDJAN":  "DISTRICT AUTONOME D ABIDJAN",
    "IDSTIRCTAUTONOMEDEYAMOUSSOUKRO": "DISTRICT AUTONOME DE YAMOUSSOUKRO",
    "AUOBIJD-HOL":                 "DISTRICT AUTONOME D ABIDJAN",
    "INDEIN-EDJUABILN":            "INDENIE-DJUABLIN",
    "LAME":                        "LA ME",
    "LO-HDIJBOUA":                 "LOH-DJIBOUA",
    "SA-NPEDRO":                   "SAN-PEDRO",
    "SU-DCOMOE":                   "SUD-COMOE",
    "TONKIP":                      "TONKPI",
    "EOMOC-DUS":                   "SUD-COMOE",
    "ARDNASSAS-TUAH":              "HAUT-SASSANDRA",
    "AWAN":                        "NAWA",
    "EKEBG":                       "GBEKE",
    "ELKOBG":                      "GBOKLE",
    "EMAL":                        "LA ME",
    "EOMOC-DUS":                   "SUD-COMOE",
    "EREB":                        "BERE",
    "EUOGAB":                      "BAGOUE",
    "'NIZ":                       "N ZI",
    "KABADOUGOU":                  "KABADOUGOU",
    "CAVALLY":                     "CAVALLY",
    "BAGOUE":                      "BAGOUE",
    "BERE":                        "BERE",
    "FOLON":                       "FOLON",
    "GBEKE":                       "GBEKE",
    "GBOKLE":                      "GBOKLE",
    "GOH":                         "GOH",
    "HAMBOL":                      "HAMBOL",
    "IFFOU":                       "IFFOU",
    "MARAHOUE":                    "MARAHOUE",
    "MORONOU":                     "MORONOU",
    "NAWA":                        "NAWA",
    "PORO":                        "PORO",
    "TCHOLOGO":                    "TCHOLOGO",
    "WORODOUGOU":                  "WORODOUGOU",
    "INCONNUE":                    "INCONNUE",
}


def decode_region(raw):
    """
    Decode le nom de region ecrit verticalement dans le PDF.
    Utilise un dictionnaire de corrections pour les cas ambigus.
    """
    if not raw:
        return None
    fragments = raw.split("\n")
    # Essai 1 : ordre normal
    joined_normal = re.sub(r"\s+", "", "".join(fragments)).upper()
    if joined_normal in REGION_MAP:
        return REGION_MAP[joined_normal]
    if joined_normal in REGION_MAP.values():
        return joined_normal
    # Essai 2 : ordre inverse
    joined_reverse = re.sub(r"\s+", "", "".join(fragments[::-1])).upper()
    if joined_reverse in REGION_MAP:
        return REGION_MAP[joined_reverse]
    if joined_reverse in REGION_MAP.values():
        return joined_reverse
    # Retourner le nom brut si pas trouve
    return joined_normal if len(joined_normal) > 2 else None


# Colonnes du tableau (index 0 a 15)
# 0  = REGION (vertical)
# 1  = numero circo
# 2  = nom circo
# 3  = NB BV
# 4  = INSCRITS
# 5  = VOTANTS
# 6  = TAUX PARTICIPATION
# 7  = BULLETINS NULS
# 8  = SUFFRAGES EXPRIMES
# 9  = BULLETINS BLANCS (NOMBRE)
# 10 = BULLETINS BLANCS (%)
# 11 = PARTI
# 12 = CANDIDAT
# 13 = SCORE
# 14 = POURCENTAGE
# 15 = ELU(E)

COL_REGION   = 0
COL_NUM      = 1
COL_CIRCO    = 2
COL_NBBV     = 3
COL_INSCRITS = 4
COL_VOTANTS  = 5
COL_TAUX     = 6
COL_NULS     = 7
COL_EXPRIMES = 8
COL_BLANCS   = 9
COL_PARTI    = 11
COL_CANDIDAT = 12
COL_SCORE    = 13
COL_PCT      = 14
COL_ELU      = 15


def to_int(val):
    """Convertit "52 106" ou "52106" en 52106."""
    if val is None:
        return None
    try:
        return int(str(val).replace(" ", "").replace("\n", "").strip())
    except (ValueError, TypeError):
        return None


def to_float_pct(val):
    """Convertit "27,00%" en 27.0."""
    if val is None:
        return None
    try:
        s = str(val).replace("%", "").replace(",", ".").strip()
        return float(s)
    except (ValueError, TypeError):
        return None


def is_header_row(row):
    """Detecte les lignes d en-tete a ignorer."""
    if not row or not any(row):
        return True
    first_cells = [str(c or "").strip() for c in row[:4]]
    joined = " ".join(first_cells).upper()
    return any(h in joined for h in [
        "REGI", "CIRCONSCRIPTION", "NB BV", "TOTAL",
        "GROUPEMENTS", "CANDIDATS", "TAUX DE"
    ])


def is_valid_candidate_row(parti, candidat, score_str):
    """Verifie qu une ligne contient bien un candidat valide."""
    if not parti or not candidat or not score_str:
        return False
    parti_clean = str(parti).strip().upper()
    candidat_clean = str(candidat).strip()
    score_clean = str(score_str).replace(" ", "").strip()
    
    # Le parti doit etre non vide et pas un en-tete
    if len(parti_clean) < 2:
        return False
    if parti_clean in ["GROUPEMENTS", "POLITIQUES", "PARTIS"]:
        return False
    
    # Le candidat doit avoir au moins 3 caracteres
    if len(candidat_clean) < 3:
        return False
    
    # Le score doit etre un nombre valide
    try:
        score = int(score_clean)
        return score > 0
    except (ValueError, TypeError):
        return False


def extract_raw_tables(pdf_path):
    """
    Extrait toutes les lignes candidats du PDF en utilisant
    l API extract_tables() de pdfplumber.
    
    Structure du tableau PDF (16 colonnes) :
    [region_vertical | num_circo | nom_circo | nb_bv | inscrits | votants |
     taux | nuls | exprimes | blancs_nb | blancs_pct |
     parti | candidat | score | pct_score | elu]
    """
    raw_rows = []
    
    current_region = None
    current_circo  = None
    current_stats  = {}

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            
            tables = page.extract_tables({
                "vertical_strategy":   "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance":       3,
            })
            
            if not tables:
                continue
            
            # Le PDF a une seule grande table par page
            table = tables[0]
            
            for row in table:
                # Ignorer les lignes vides ou en-tetes
                if is_header_row(row):
                    continue
                
                # S assurer que la ligne a assez de colonnes
                while len(row) < 16:
                    row.append(None)
                
                # --- Detecter une nouvelle region ---
                region_raw = row[COL_REGION]
                if region_raw and str(region_raw).strip():
                    decoded = decode_region(str(region_raw))
                    if decoded and len(decoded) > 2:
                        current_region = decoded
                
                # --- Detecter une nouvelle circonscription ---
                num_circo  = row[COL_NUM]
                nom_circo  = row[COL_CIRCO]
                taux_raw   = row[COL_TAUX]
                
                if num_circo and str(num_circo).strip().isdigit() and nom_circo:
                    current_circo = str(nom_circo).replace("\n", " ").strip()
                    current_stats = {
                        "nb_bv":              to_int(row[COL_NBBV]),
                        "inscrits":           to_int(row[COL_INSCRITS]),
                        "votants":            to_int(row[COL_VOTANTS]),
                        "taux_participation": to_float_pct(taux_raw),
                        "bulletins_nuls":     to_int(row[COL_NULS]),
                        "suffrages_exprimes": to_int(row[COL_EXPRIMES]),
                        "bulletins_blancs":   to_int(row[COL_BLANCS]),
                    }
                
                # --- Detecter un candidat ---
                parti    = row[COL_PARTI]
                candidat = row[COL_CANDIDAT]
                score    = row[COL_SCORE]
                pct      = row[COL_PCT]
                elu_val  = row[COL_ELU]
                
                if not is_valid_candidate_row(parti, candidat, score):
                    continue
                
                if not current_circo:
                    continue
                
                raw_rows.append({
                    "page":            page_num,
                    "region":          current_region or "INCONNUE",
                    "circonscription": current_circo,
                    **current_stats,
                    "parti":           str(parti).strip().upper(),
                    "candidat":        str(candidat).replace("\n", " ").strip(),
                    "score":           to_int(score),
                    "pct_score":       to_float_pct(pct),
                    "elu":             bool(elu_val and "ELU" in str(elu_val).upper()),
                })
    
    return raw_rows
