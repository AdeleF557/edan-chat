import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from app.config import APP_TITLE, DB_PATH
from agent.sql_agent import answer
from agent.chart_gen import auto_chart, turnout_chart
from ingestion.load import get_connection

st.set_page_config(page_title="EDAN 2025", page_icon="elections", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({
        "role": "assistant",
        "content": (
            "Bonjour ! Je suis l assistant d analyse des elections legislatives "
            "ivoiriennes du 27 decembre 2025.\n\n"
            "Exemples de questions :\n"
            "- Combien de sieges le RHDP a-t-il obtenus ?\n"
            "- Taux de participation par region\n"
            "- Top 10 candidats avec le plus de voix\n"
            "- Histogramme des gagnants par parti"
        ),
        "dataframe": None,
        "sql": None,
        "chart_type": None,
        "question": "",
    })


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


with st.sidebar:
    st.title("EDAN 2025")
    st.divider()
    if check_db():
        st.success("Base de donnees prete")
    else:
        st.error("Base non initialisee. Lancez : make ingest")
    st.divider()
    show_sql = st.toggle("Afficher le SQL genere", value=False)
    st.divider()
    st.caption("Source : CEI - Cote dIvoire, 27 dec. 2025")


st.title("Chat — Resultats Elections EDAN 2025")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        if msg.get("dataframe") is not None and not msg["dataframe"].empty:
            with st.expander("Voir les donnees brutes"):
                st.dataframe(msg["dataframe"], use_container_width=True)

        if msg.get("chart_type") and msg["chart_type"] != "none":
            if msg.get("dataframe") is not None and not msg["dataframe"].empty:
                fig = auto_chart(
                    msg["dataframe"],
                    msg["chart_type"],
                    question=msg.get("question", ""),
                )
                if fig:
                    st.plotly_chart(fig, use_container_width=True)

        if show_sql and msg.get("sql"):
            with st.expander("SQL execute"):
                st.code(msg["sql"], language="sql")


if prompt := st.chat_input("Posez votre question sur les elections..."):
    if not check_db():
        st.error("Lancez d abord : make ingest")
        st.stop()

    with st.chat_message("user"):
        st.markdown(prompt)

    st.session_state.messages.append({
        "role": "user",
        "content": prompt,
        "dataframe": None,
        "sql": None,
        "chart_type": None,
        "question": prompt,
    })

    with st.chat_message("assistant"):
        with st.spinner("Analyse en cours..."):
            result = answer(prompt)

        st.markdown(result["text"])

        if result.get("dataframe") is not None and not result["dataframe"].empty:
            with st.expander("Voir les donnees brutes"):
                st.dataframe(result["dataframe"], use_container_width=True)

        if result.get("chart_type") and result["chart_type"] != "none":
            if result.get("dataframe") is not None and not result["dataframe"].empty:
                df_chart = result["dataframe"]
                # Utiliser le graphique specialise si taux de participation
                if "avg_taux_participation" in df_chart.columns:
                    fig = turnout_chart(df_chart, title=prompt[:60])
                else:
                    fig = auto_chart(df_chart, result["chart_type"], question=prompt)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)

        if show_sql and result.get("sql"):
            with st.expander("SQL execute"):
                st.code(result["sql"], language="sql")

    st.session_state.messages.append({
        "role": "assistant",
        "content": result["text"],
        "dataframe": result.get("dataframe"),
        "sql": result.get("sql"),
        "chart_type": result.get("chart_type"),
        "question": prompt,
    })
