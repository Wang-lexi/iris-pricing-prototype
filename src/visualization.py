"""Plotly charts for the pocket price waterfall."""

import textwrap

import pandas as pd
import plotly.graph_objects as go

TOTAL_COLOR = "#3b6ea5"    # running totals: list, invoice, pocket revenue
LOSS_COLOR = "#d9822b"     # deductions
MARGIN_COLOR = "#2a9d8f"   # final pocket margin
SELECTED_COLOR = "#2a9d8f"  # comparison charts: the selected product / customer
REF_COLOR = "#8a9bb0"       # comparison charts: the reference group
GRID = "rgba(128,128,128,0.25)"


def money(x: float) -> str:
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e6:
        return f"{sign}${x / 1e6:,.2f}M"
    if x >= 1e4:
        return f"{sign}${x / 1e3:,.0f}K"
    return f"{sign}${x:,.0f}"  # small amounts (single transactions) in exact dollars


def _wrap(label: str, width: int = 12) -> str:
    """Break a long label over several lines so the axis text stays horizontal."""
    return "<br>".join(textwrap.wrap(label, width=width)) or label


def waterfall_chart(wf: pd.DataFrame, height: int = 560) -> go.Figure:
    """Staircase waterfall that flows down from one horizontal level.

    - First bar (list revenue) and last bar (pocket margin) stand on zero.
    - Every deduction is an orange bar that starts where the previous step ended and
      drops down, so the chart reads left to right as a descending staircase.
    - Subtotals in the middle (invoice revenue, pocket revenue) are drawn only as a
      horizontal level line, not as a tall column.
    """
    n = len(wf)
    xs = list(range(n))
    labels = [_wrap(s) for s in wf["label"]]
    amounts = list(wf["amount_cad"])
    pcts = list(wf["pct_of_list"])
    kinds = list(wf["kind"])

    ends, drops, levels_marks = {"x": [], "y": [], "t": [], "h": []}, \
        {"x": [], "y": [], "base": [], "t": [], "h": []}, {"x": [], "y": [], "t": []}
    level = 0.0
    level_after = []
    for i in range(n):
        amt, pct = amounts[i], pcts[i]
        hover = f"{wf['label'].iloc[i]}<br>{amt:,.0f} CAD<br>{pct:.2%} of list revenue"
        text = f"{money(amt)}<br>{pct:.1%}"
        if kinds[i] == "total":
            level = amt
            if i in (0, n - 1):  # start and end: full bars on zero
                ends["x"].append(i); ends["y"].append(amt)
                ends["t"].append(text); ends["h"].append(hover)
            else:                 # subtotal: a level line only
                levels_marks["x"].append(i); levels_marks["y"].append(amt)
                levels_marks["t"].append(text)
        else:
            before, level = level, level + amt
            drops["x"].append(i); drops["y"].append(abs(amt))
            drops["base"].append(min(before, level))
            drops["t"].append(text); drops["h"].append(hover)
        level_after.append(level)

    fig = go.Figure()
    fig.add_bar(name="Start / end total", x=ends["x"], y=ends["y"], width=0.8,
                marker_color=[TOTAL_COLOR] + [MARGIN_COLOR] * (len(ends["x"]) - 1),
                text=ends["t"], textposition="outside", cliponaxis=False,
                hovertext=ends["h"], hoverinfo="text")
    fig.add_bar(name="Deduction (money taken out)", x=drops["x"], y=drops["y"],
                base=drops["base"], width=0.8, marker_color=LOSS_COLOR,
                text=drops["t"], textposition="outside", cliponaxis=False,
                hovertext=drops["h"], hoverinfo="text")
    for j, (x, y) in enumerate(zip(levels_marks["x"], levels_marks["y"])):
        fig.add_scatter(x=[x - 0.4, x + 0.4], y=[y, y], mode="lines",
                        line=dict(color=TOTAL_COLOR, width=4),
                        name="Subtotal level", legendgroup="level",
                        showlegend=(j == 0), hoverinfo="skip")
    top = max(max(ends["y"], default=0), max(levels_marks["y"], default=0))
    fig.add_scatter(x=levels_marks["x"], y=[y + top * 0.045 for y in levels_marks["y"]],
                    mode="text", text=levels_marks["t"], textposition="middle center",
                    showlegend=False, hoverinfo="skip")
    for i in range(n - 1):  # thin horizontal connectors: the staircase "flow"
        fig.add_shape(type="line", x0=i + 0.4, x1=i + 0.6,
                      y0=level_after[i], y1=level_after[i],
                      line=dict(color=GRID, width=1))

    fig.update_layout(
        height=height, bargap=0, margin=dict(t=50, b=10, l=10, r=10),
        legend=dict(orientation="h", y=1.1, x=0),
        yaxis=dict(title="CAD", gridcolor=GRID, tickformat="$,.2s", automargin=True,
                   range=[0, top * 1.15]),
        xaxis=dict(tickmode="array", tickvals=xs, ticktext=labels, tickangle=0,
                   tickfont=dict(size=12), automargin=True, range=[-0.6, n - 0.4],
                   showgrid=False),
    )
    return fig


def compare_chart(rows: pd.DataFrame, name_a: str, name_b: str, height: int = 420) -> go.Figure:
    """Grouped bars: each step as % of list revenue, selected group vs reference.

    `rows` needs columns: label, selected, reference (fractions of list revenue).
    """
    labels = [_wrap(s) for s in rows["label"]]
    fig = go.Figure()
    fig.add_bar(name=name_b, x=labels, y=rows["reference"], marker_color=REF_COLOR,
                text=[f"{v:.2%}" for v in rows["reference"]], textposition="outside",
                cliponaxis=False)
    fig.add_bar(name=name_a, x=labels, y=rows["selected"], marker_color=SELECTED_COLOR,
                text=[f"{v:.2%}" for v in rows["selected"]], textposition="outside",
                cliponaxis=False)
    fig.update_layout(
        barmode="group", bargap=0.2, height=height, margin=dict(t=50, b=10, l=10, r=10),
        legend=dict(orientation="h", y=1.1, x=0),
        yaxis=dict(title="% of list revenue", tickformat=".1%", gridcolor=GRID,
                   rangemode="tozero", automargin=True),
        xaxis=dict(categoryorder="array", categoryarray=labels, tickangle=0,
                   automargin=True),
    )
    return fig
