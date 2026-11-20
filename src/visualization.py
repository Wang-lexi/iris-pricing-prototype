"""Plotly chart for the pocket price waterfall."""

import pandas as pd
import plotly.graph_objects as go

TOTAL_COLOR = "#3b6ea5"   # list, invoice, pocket revenue, margin
LOSS_COLOR = "#d9822b"    # deductions
GRID = "rgba(128,128,128,0.25)"


def money(x: float) -> str:
    sign = "-" if x < 0 else ""
    x = abs(x)
    return f"{sign}${x / 1e6:,.2f}M" if x >= 1e6 else f"{sign}${x / 1e3:,.0f}K"


def waterfall_chart(wf: pd.DataFrame) -> go.Figure:
    # First bar is the starting value ("absolute"); later subtotals ("total") are
    # drawn from zero up to the running sum; deductions are "relative" steps.
    measure = ["relative" if k == "delta" else ("absolute" if i == 0 else "total")
               for i, k in enumerate(wf["kind"])]
    text = [f"{money(a)}<br>{p:.1%}" for a, p in zip(wf["amount_cad"], wf["pct_of_list"])]
    fig = go.Figure(go.Waterfall(
        x=wf["label"], y=wf["amount_cad"], measure=measure,
        text=text, textposition="outside",
        connector={"line": {"color": GRID}},
        increasing={"marker": {"color": TOTAL_COLOR}},
        decreasing={"marker": {"color": LOSS_COLOR}},
        totals={"marker": {"color": TOTAL_COLOR}},
        # 'absolute' bars take the "increasing" colour, so both are the same blue.
        hovertemplate="%{x}<br>%{y:$,.0f}<extra></extra>",
    ))
    fig.update_layout(
        showlegend=False, height=540, margin=dict(t=30, b=10, l=10, r=10),
        yaxis=dict(title="CAD", gridcolor=GRID, tickformat="$,.2s"),
        xaxis=dict(tickangle=-30),
    )
    return fig
