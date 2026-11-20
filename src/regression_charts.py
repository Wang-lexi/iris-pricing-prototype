"""Plotly charts for the regression diagnosis page."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .regression import PREDICTED, RESIDUAL, TARGET

NORMAL_COLOR = "#8a9bb0"
OUTLIER_COLOR = "#d9822b"   # statistical outlier
POLICY_COLOR = "#b23a48"    # discount above the contract limit
BOTH_COLOR = "#6a3d9a"
POSITIVE_COLOR = "#d9822b"  # driver raises the reduction
NEGATIVE_COLOR = "#3b6ea5"  # driver lowers the reduction
GRID = "rgba(128,128,128,0.25)"


def _status(df: pd.DataFrame) -> pd.Series:
    stat, policy = df["statistical_exception"], df["policy_exception"]
    label = np.select([stat & policy, stat, policy],
                      ["Both", "Statistical outlier", "Contract policy exception"],
                      default="Within expected range")
    return pd.Series(label, index=df.index)


def actual_vs_predicted_chart(df: pd.DataFrame, height: int = 520) -> go.Figure:
    """Predicted (x) against actual (y) reduction rate. Points above the line got more."""
    status = _status(df)
    styles = [("Within expected range", NORMAL_COLOR, 0.35, 5),
              ("Statistical outlier", OUTLIER_COLOR, 0.9, 8),
              ("Contract policy exception", POLICY_COLOR, 0.9, 8),
              ("Both", BOTH_COLOR, 0.95, 9)]
    fig = go.Figure()
    for name, color, opacity, size in styles:
        part = df[status == name]
        if part.empty:
            continue
        fig.add_trace(go.Scattergl(
            x=part[PREDICTED] * 100, y=part[TARGET] * 100, mode="markers", name=name,
            marker=dict(color=color, opacity=opacity, size=size),
            customdata=part.assign(residual_pp=part[RESIDUAL] * 100)[
                ["transaction_id", "customer_name", "residual_pp"]],
            hovertemplate=("%{customdata[0]} · %{customdata[1]}<br>predicted %{x:.1f}%"
                           "<br>actual %{y:.1f}%<br>residual %{customdata[2]:+.1f} pp<extra></extra>")))
    top = max(df[TARGET].max(), df[PREDICTED].max()) * 100
    fig.add_trace(go.Scatter(x=[0, top], y=[0, top], mode="lines", name="Actual = predicted",
                             line=dict(color="#555", dash="dash", width=1), hoverinfo="skip"))
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="white",
        legend=dict(orientation="h", y=1.08, x=0),
        xaxis=dict(title="Predicted reduction rate (% of list revenue)", gridcolor=GRID,
                   ticksuffix="%", zeroline=False),
        yaxis=dict(title="Actual reduction rate (% of list revenue)", gridcolor=GRID,
                   ticksuffix="%", zeroline=False))
    return fig


def drivers_chart(coefs: pd.DataFrame, height: int | None = None, show_ci: bool = True) -> go.Figure:
    """Effect of each driver in percentage points of list revenue (optionally with 95% intervals)."""
    c = coefs.reindex(coefs["coef_pp"].abs().sort_values().index)
    colors = [POSITIVE_COLOR if v > 0 else NEGATIVE_COLOR for v in c["coef_pp"]]
    fig = go.Figure(go.Bar(
        x=c["coef_pp"], y=c["label"], orientation="h", marker_color=colors,
        text=[f"{v:+.1f} pp" for v in c["coef_pp"]], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>%{x:+.2f} pp<extra></extra>"))
    if show_ci:
        fig.update_traces(error_x=dict(
            type="data", symmetric=False, array=c["ci_high_pp"] - c["coef_pp"],
            arrayminus=c["coef_pp"] - c["ci_low_pp"], color="#444", thickness=1))
    fig.update_layout(
        height=height or max(360, 22 * len(c) + 80), margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="white", showlegend=False,
        xaxis=dict(title="Effect on reduction rate (percentage points of list revenue)",
                   gridcolor=GRID, zerolinecolor="#555"),
        yaxis=dict(automargin=True))
    return fig
