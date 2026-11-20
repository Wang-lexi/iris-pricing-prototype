"""Plotly chart for the pocket price waterfall."""

import pandas as pd
import plotly.graph_objects as go

TOTAL_COLOR = "#3b6ea5"   # list, invoice, pocket revenue, margin
LOSS_COLOR = "#d9822b"    # deductions
GRID = "rgba(128,128,128,0.25)"


def money(x: float) -> str:
    return f"${x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"${x / 1e3:,.0f}K"


def waterfall_chart(wf: pd.DataFrame) -> go.Figure:
    measure = ["total" if k == "total" else "relative" for k in wf["kind"]]
    text = [f"{money(a)}<br>{p:.1%}" for a, p in zip(wf["amount_cad"], wf["pct_of_list"])]
    fig = go.Figure(go.Waterfall(
        x=wf["label"], y=wf["amount_cad"], measure=measure,
        text=text, textposition="outside",
        connector={"line": {"color": GRID}},
        increasing={"marker": {"color": TOTAL_COLOR}},
        decreasing={"marker": {"color": LOSS_COLOR}},
        totals={"marker": {"color": TOTAL_COLOR}},
        hovertemplate="%{x}<br>%{y:$,.0f}<extra></extra>",
    ))
    fig.update_layout(
        showlegend=False, height=540, margin=dict(t=30, b=10, l=10, r=10),
        yaxis=dict(title="CAD", gridcolor=GRID, tickformat="$,.2s"),
        xaxis=dict(tickangle=-30),
    )
    return fig
