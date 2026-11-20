"""Plotly charts for the pricing dashboard."""

import pandas as pd
import plotly.graph_objects as go

from src.pricing_analysis import DEDUCTIONS

TOTAL_COLOR = "#3b6ea5"   # subtotals (list, invoice, pocket revenue)
LOSS_COLOR = "#d9822b"    # money leaking out
MARGIN_COLOR = "#2a9d8f"  # final pocket margin
NEG_COLOR = "#c0392b"
GRID = "rgba(128,128,128,0.25)"


def _money(x: float) -> str:
    return f"${x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"${x / 1e3:,.0f}K"


def waterfall_chart(wf: pd.DataFrame) -> go.Figure:
    """Classic price waterfall from the output of `waterfall_totals`."""
    # 'total' bars are drawn from zero (list, invoice, pocket revenue, margin).
    measure = ["total" if k == "total" else "relative" for k in wf["kind"]]
    text = [f"{_money(a)}<br>{p:.1%}" for a, p in zip(wf["amount_cad"], wf["pct_of_list"])]

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
        showlegend=False, height=520, margin=dict(t=30, b=10, l=10, r=10),
        yaxis=dict(title="CAD", gridcolor=GRID, tickformat="$,.2s"),
        xaxis=dict(tickangle=-30),
    )
    return fig


def leakage_stack_chart(seg: pd.DataFrame, by: str) -> go.Figure:
    """Stacked bars: each deduction as a % of list revenue, per segment."""
    palette = ["#d9822b", "#e9b44c", "#7fb069", "#6c8ead", "#9d7bb0"]
    fig = go.Figure()
    for (col, label), color in zip(DEDUCTIONS, palette):
        fig.add_bar(name=label, x=seg[by].astype(str), y=seg[f"{col}_rate"],
                    marker_color=color,
                    hovertemplate=f"{label}: %{{y:.2%}}<extra></extra>")
    fig.update_layout(
        barmode="stack", height=420, margin=dict(t=30, b=10, l=10, r=10),
        yaxis=dict(title="% of list revenue", tickformat=".0%", gridcolor=GRID),
        legend=dict(orientation="h", y=-0.25),
    )
    return fig


def whale_chart(w: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=w["cum_customers_pct"], y=w["cum_margin_pct"], mode="lines",
        line=dict(color=TOTAL_COLOR, width=3),
        hovertemplate="Top %{x:.0%} of customers<br>%{y:.0%} of pocket margin<extra></extra>",
    ))
    fig.add_hline(y=1, line_dash="dot", line_color=GRID)
    fig.update_layout(
        height=420, margin=dict(t=30, b=10, l=10, r=10),
        xaxis=dict(title="Customers ranked by pocket margin (cumulative %)",
                   tickformat=".0%", gridcolor=GRID),
        yaxis=dict(title="Cumulative pocket margin (% of total)",
                   tickformat=".0%", gridcolor=GRID),
    )
    return fig
