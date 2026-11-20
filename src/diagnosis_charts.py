"""Plotly charts for the root cause and scenario page."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

GRID = "rgba(128,128,128,0.25)"
ABOVE_PEERS = "#d9822b"
BELOW_PEERS = "#3b6ea5"
ORIGINAL = "#8a9bb0"
SIMULATED = "#2a9d8f"


def component_excess_chart(table: pd.DataFrame, height: int = 300) -> go.Figure:
    """How far each deduction is above (orange) or below (blue) its tier peers."""
    t = table.iloc[::-1]
    fig = go.Figure(go.Bar(
        x=t["excess_pp"], y=t["component"], orientation="h",
        marker_color=[ABOVE_PEERS if v > 0 else BELOW_PEERS for v in t["excess_pp"]],
        text=[f"{v:+.2f} pp" for v in t["excess_pp"]], textposition="outside", cliponaxis=False,
        customdata=t[["pct_of_list", "peer_median_pct"]],
        hovertemplate="%{y}<br>this transaction %{customdata[0]:.2f}% of list<br>"
                      "peer median %{customdata[1]:.2f}%<extra></extra>"))
    fig.update_layout(
        height=height, margin=dict(l=10, r=40, t=10, b=10), plot_bgcolor="white", showlegend=False,
        xaxis=dict(title="Above (+) or below (-) what similar customers typically get, in points of list price",
                   gridcolor=GRID, zerolinecolor="#555"),
        yaxis=dict(automargin=True))
    return fig


def comparison_chart(original: dict, simulated: dict, height: int = 380) -> go.Figure:
    """Original against simulated invoice revenue, pocket revenue and pocket margin (CAD)."""
    labels = ["Invoice revenue", "Pocket revenue", "Pocket margin"]
    keys = ["invoice_revenue_cad", "pocket_revenue_cad", "pocket_margin_cad"]
    fig = go.Figure()
    for name, src, color, pattern in [("Original", original, ORIGINAL, ""),
                                      ("Simulated (hypothetical)", simulated, SIMULATED, "/")]:
        values = [src[k] for k in keys]
        fig.add_trace(go.Bar(
            name=name, x=labels, y=values, marker_color=color, marker_pattern_shape=pattern,
            text=[f"${v:,.0f}" for v in values], textposition="outside", cliponaxis=False))
    fig.update_layout(
        barmode="group", height=height, margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="white",
        legend=dict(orientation="h", y=1.1, x=0),
        yaxis=dict(title="CAD", gridcolor=GRID, tickformat=","))
    return fig
