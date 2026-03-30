import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from app.config import APP_TITLE, DB_PATH
from agent.sql_agent import answer
from agent.chart_gen import auto_chart, turnout_chart
from ingestion.load import get_connection

st.set_page_config(page_title="EDAN 2025", page_icon="🗳️", layout="wide")

st.markdown("""
<style>
[data-testid="stDataFrame"] {
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid rgba(128,128,128,0.2);
}
.route-badge {
    display: inline-block;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    margin-bottom: 6px;
    font-weight: 600;
    letter-spacing: 0.5px;
}
.route-sql  { background: #e3f2fd; color: #1565c0; }
.route-rag  { background: #f3e5f5; color: #6a1b9a; }
.source-pill {
    display: inline-block;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    background: #f5f5f5;
    color: #555;
    margin: 2px 3px 2px 0;
    border: 1px solid #e0e0e0;
}
</style>
""", unsafe_allow_html=True)

# ── Initialisation session ───────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({
        "role":       "assistant",
        "content":    (
            "Bonjour ! Je suis l'assistant d'analyse des élections législatives "
            "ivoiriennes du 27 décembre 2025.\n\n"
            "**Exemples de questions :**\n"
            "- Combien de sièges le RHDP a-t-il obtenus ?\n"
            "- Taux de participation par région\n"
            "- Top 10 candidats avec le plus de voix\n"
            "- Histogramme des gagnants par parti"
        ),
        "dataframe":  None,
        "sql":        None,
        "chart_type": None,
        "question":   "",
        "route":      None,
        "ambiguous":         False,
        "ambiguity_options": [],
        "citations":         [],
    })

# Session context pour Level 3 (entités résolues persistent)
if "session_context" not in st.session_state:
    st.session_state.session_context = {}


def check_db():
    if not DB_PATH.exists():
        return False
    try:
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM election_results").fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def _render_sql_sources(df):
    """
    Affiche les numéros de pages PDF comme citations pour les réponses SQL.
    Utilise la colonne 'page' si elle est présente dans le DataFrame.
    """
    if df is None or df.empty:
        return
    if "page" not in df.columns:
        return
    pages = sorted(df["page"].dropna().unique().astype(int).tolist())
    if not pages:
        return
    pills_html = "".join(
        f'<span class="source-pill">📄 p.{p}</span>' for p in pages
    )
    st.markdown(
        f"<div style='margin-top:4px'><strong style='font-size:12px;"
        f"color:#888'>Sources PDF :</strong> {pills_html}</div>",
        unsafe_allow_html=True,
    )


def _update_session_context(result: dict):
    """
    Met à jour le contexte de session avec les entités résolues
    par le fuzzy matching ET depuis le dernier résultat SQL.
    """
    # 1. Entités corrigées par le fuzzy
    corrections = result.get("corrections", [])
    for c in corrections:
        if c.get("entity_type") in ("region", "circonscription", "parti"):
            st.session_state.session_context[c["entity_type"]] = c["matched"]

    df = result.get("dataframe")

    # 2. Région unique détectée dans le résultat SQL → mémoriser
    if df is not None and not df.empty and "region" in df.columns:
        regions = df["region"].dropna().unique().tolist()
        if len(regions) == 1:
            st.session_state.session_context["region"] = regions[0]

    # 3. Parti unique détecté dans le résultat SQL → mémoriser comme dernier_parti
    if df is not None and not df.empty and "parti" in df.columns:
        partis = df["parti"].dropna().unique().tolist()
        if len(partis) == 1:
            st.session_state.session_context["dernier_parti"] = partis[0]

    # 4. Circonscription unique → mémoriser
    if df is not None and not df.empty and "circonscription" in df.columns:
        circos = df["circonscription"].dropna().unique().tolist()
        if len(circos) == 1:
            st.session_state.session_context["circonscription"] = circos[0]

def render_result(msg, show_sql=False):
    """
    Affiche un message assistant avec :
    - badge de route (SQL / RAG)
    - texte explicatif
    - tableau + sources PDF (SQL) ou citations page (RAG)
    - boutons de clarification si ambiguïté (Level 3)
    - graphique
    - SQL optionnel
    """
    route = msg.get("route")
    if route in ("sql", "rag_fallback", "rag_exec_fallback"):
        st.markdown('<span class="route-badge route-sql">⚡ SQL</span>',
                    unsafe_allow_html=True)
    elif route in ("rag", "rag_from_oos"):
        st.markdown('<span class="route-badge route-rag">🔍 RAG</span>',
                    unsafe_allow_html=True)

    # Texte explicatif
    st.markdown(msg["content"])

    # ── Tableau + sources ──────────────────────────────────────────
    df = msg.get("dataframe")
    if df is not None and not df.empty:
        # Colonnes à masquer dans l'affichage (internes)
        cols_to_hide = {"page", "search_circo", "id"}
        df_display = df[[c for c in df.columns if c not in cols_to_hide]].copy()
        for col in df_display.select_dtypes(include=["float64"]).columns:
            df_display[col] = df_display[col].round(2)

        st.dataframe(df_display, use_container_width=True, hide_index=True)

        # Sources PDF depuis la colonne page (SQL)
        _render_sql_sources(df)

        # ── Graphique ──────────────────────────────────────────────
        chart_type = msg.get("chart_type")
        if chart_type and chart_type != "none":
            if "avg_taux_participation" in df.columns:
                fig = turnout_chart(df, title=msg.get("question", "")[:60])
            else:
                fig = auto_chart(df, chart_type, question=msg.get("question", ""))
            if fig:
                st.plotly_chart(fig, use_container_width=True)

    # ── Boutons de clarification Level 3 ──────────────────────────
    if msg.get("ambiguous") and msg.get("ambiguity_options"):
        options = msg["ambiguity_options"]
        st.markdown("**Précisez la circonscription souhaitée :**")
        # Afficher max 6 options en grille de 2 colonnes
        pairs = [options[i:i+2] for i in range(0, min(len(options), 6), 2)]
        for pair in pairs:
            cols = st.columns(len(pair))
            for col, option in zip(cols, pair):
                # Clé unique basée sur le contenu du message
                btn_key = f"amb_{hash(msg['content'])}_{option[:15]}"
                with col:
                    if st.button(
                        option[:50] + ("…" if len(option) > 50 else ""),
                        key=btn_key,
                        use_container_width=True,
                    ):
                        # Mémoriser le choix en session
                        st.session_state.session_context["circonscription"] = option
                        # Injecter la question précisée dans le chat
                        new_q = f"Résultats pour la circonscription : {option}"
                        st.session_state.messages.append({
                            "role": "user", "content": new_q,
                            "dataframe": None, "sql": None,
                            "chart_type": None, "question": new_q,
                            "route": None, "ambiguous": False,
                            "ambiguity_options": [], "citations": [],
                        })
                        st.rerun()

    # SQL optionnel
    if show_sql and msg.get("sql"):
        with st.expander("🔍 SQL exécuté"):
            st.code(msg["sql"], language="sql")


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🗳️ EDAN 2025")
    st.divider()
    if check_db():
        st.success("✅ Base de données prête")
    else:
        st.error("❌ Base non initialisée.\nLancez : `make ingest`")
    st.divider()
    show_sql = st.toggle("Afficher le SQL généré", value=False)

    # Afficher le contexte de session si non vide
    if st.session_state.session_context:
        st.divider()
        st.caption("🧠 Contexte mémorisé")
        for k, v in st.session_state.session_context.items():
            st.caption(f"• **{k}** : {v[:35]}")
        if st.button("Effacer la mémoire", use_container_width=True):
            st.session_state.session_context = {}
            st.rerun()

    st.divider()
    st.caption("Source : CEI - Côte d'Ivoire, 27 déc. 2025")


# ── Titre ─────────────────────────────────────────────────────────────────────
st.title("💬 Chat — Résultats Elections EDAN 2025")

# ── Historique ────────────────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        render_result(msg, show_sql=show_sql)

# ── Input utilisateur ─────────────────────────────────────────────────────────
if prompt := st.chat_input("Posez votre question sur les élections..."):
    if not check_db():
        st.error("Lancez d'abord : `make ingest`")
        st.stop()

    with st.chat_message("user"):
        st.markdown(prompt)

    st.session_state.messages.append({
        "role": "user", "content": prompt,
        "dataframe": None, "sql": None,
        "chart_type": None, "question": prompt,
        "route": None, "ambiguous": False,
        "ambiguity_options": [], "citations": [],
    })

    with st.chat_message("assistant"):
        with st.spinner("Analyse en cours..."):
            result = answer(
                prompt,
                history=st.session_state.messages,
                session_context=st.session_state.session_context,
            )

        # Mettre à jour le contexte de session avec les entités résolues
        _update_session_context(result)

        assistant_msg = {
            "role":              "assistant",
            "content":           result["text"],
            "dataframe":         result.get("dataframe"),
            "sql":               result.get("sql"),
            "chart_type":        result.get("chart_type"),
            "question":          prompt,
            "route":             result.get("route"),
            "ambiguous":         result.get("ambiguous", False),
            "ambiguity_options": result.get("ambiguity_options", []),
            "citations":         result.get("citations", []),
            "corrections":       result.get("corrections", []),
        }

        render_result(assistant_msg, show_sql=show_sql)

    st.session_state.messages.append(assistant_msg)