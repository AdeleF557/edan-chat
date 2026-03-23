import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def auto_chart(df, chart_type, question=""):
    if chart_type == "none" or df is None or df.empty:
        return None

    cat_cols = df.select_dtypes(include=["object", "bool"]).columns.tolist()
    num_cols = df.select_dtypes(include=["number"]).columns.tolist()

    if not cat_cols or not num_cols:
        return None

    # Choisir la meilleure colonne categorielle
    # Priorite : candidat > parti > region > premiere colonne
    preferred_cats = ["candidat", "parti", "region"]
    x_col = next((c for c in preferred_cats if c in cat_cols), cat_cols[0])

    # Choisir la meilleure colonne numerique
    # Priorite : score > nb_gagnants > avg_taux > premiere colonne
    preferred_nums = ["score", "nb_gagnants", "avg_taux_participation",
                      "total_votants", "count_star()"]
    y_col = next((c for c in preferred_nums if c in num_cols), num_cols[0])

    plot_df = df.head(20).copy()

    # Creer un label court pour l affichage
    # Si on a candidat + region, combiner les deux
    if "candidat" in plot_df.columns and "region" in plot_df.columns:
        plot_df["label"] = (
            plot_df["candidat"].str[:25] + " (" +
            plot_df["region"].str[:10] + ")"
        )
        x_col = "label"
    elif x_col in plot_df.columns:
        # Tronquer les labels trop longs
        plot_df["label"] = plot_df[x_col].astype(str).str[:30]
        x_col = "label"

    if chart_type == "pie":
        return pie_chart(plot_df, x_col, y_col, title=question[:80])
    else:
        return bar_chart(plot_df, x_col, y_col, title=question[:80])


def bar_chart(df, x, y, title=""):
    df_sorted = df.sort_values(y, ascending=True).tail(15)

    # Hauteur dynamique selon nombre de barres
    height = max(400, len(df_sorted) * 35)

    fig = px.bar(
        df_sorted,
        x=y,
        y=x,
        orientation="h",
        title=title,
        text=y,
        color=y,
        color_continuous_scale="Blues",
    )

    fig.update_traces(
        texttemplate="%{text:,}",
        textposition="outside",
        cliponaxis=False,
    )

    fig.update_layout(
        height=height,
        showlegend=False,
        coloraxis_showscale=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=200, r=80, t=50, b=40),
        xaxis=dict(
            title="",
            showgrid=True,
            gridcolor="rgba(128,128,128,0.2)",
        ),
        yaxis=dict(
            title="",
            tickfont=dict(size=12),
            automargin=True,
        ),
        title=dict(
            font=dict(size=14),
            x=0.5,
            xanchor="center",
        ),
    )

    return fig


def pie_chart(df, labels, values, title=""):
    # Tronquer les labels pour le camembert
    df = df.copy()
    df[labels] = df[labels].astype(str).str[:25]

    fig = px.pie(
        df,
        names=labels,
        values=values,
        title=title,
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )

    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        insidetextfont=dict(size=12),
        hovertemplate="<b>%{label}</b><br>Valeur: %{value:,}<br>Part: %{percent}<extra></extra>",
    )

    fig.update_layout(
        height=500,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=1.05,
            font=dict(size=11),
        ),
        title=dict(
            font=dict(size=14),
            x=0.5,
            xanchor="center",
        ),
    )

    return fig


def turnout_chart(df, title="Taux de participation par region"):
    """Graphique specialise pour le taux de participation."""
    if "region" not in df.columns or "avg_taux_participation" not in df.columns:
        return bar_chart(df,
                        df.columns[0],
                        df.columns[1],
                        title=title)

    df_sorted = df.sort_values("avg_taux_participation", ascending=True)

    fig = px.bar(
        df_sorted,
        x="avg_taux_participation",
        y="region",
        orientation="h",
        title=title,
        text="avg_taux_participation",
        color="avg_taux_participation",
        color_continuous_scale="RdYlGn",
        range_color=[0, 100],
    )

    fig.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="outside",
    )

    fig.update_layout(
        height=max(400, len(df_sorted) * 30),
        showlegend=False,
        coloraxis_showscale=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=180, r=80, t=50, b=40),
        xaxis=dict(title="Taux (%)", range=[0, 110]),
        yaxis=dict(title="", automargin=True),
    )

    return fig
