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
    """Waterfall drawn with explicit bars (full control of colour and position).

    Blue bars are running totals drawn from zero; orange bars are deductions that
    hang from the previous level; the last bar (pocket margin) is teal.
    """
    labels = [_wrap(s) for s in wf["label"]]
    groups = {"Running total": ([], [], [], [], []),
              "Deduction": ([], [], [], [], []),
              "Final pocket margin": ([], [], [], [], [])}
    colors = {"Running total": TOTAL_COLOR, "Deduction": LOSS_COLOR,
              "Final pocket margin": MARGIN_COLOR}

    level = 0.0
    levels = []  # running level after each step, used for connector lines
    last = len(wf) - 1
    for i, (amt, pct, kind) in enumerate(zip(wf["amount_cad"], wf["pct_of_list"], wf["kind"])):
        if kind == "total":
            base, height_, level = 0.0, amt, amt
            name = "Final pocket margin" if i == last else "Running total"
        else:
            before, level = level, level + amt
            base, height_ = min(before, level), abs(amt)
            name = "Deduction"
        levels.append(level)
        xs, ys, bases, texts, hovers = groups[name]
        xs.append(labels[i]); ys.append(height_); bases.append(base)
        texts.append(f"{money(amt)}<br>{pct:.1%}")
        hovers.append(f"{wf['label'].iloc[i]}<br>{amt:,.0f} CAD<br>{pct:.2%} of list revenue")

    fig = go.Figure()
    for name, (xs, ys, bases, texts, hovers) in groups.items():
        if not xs:
            continue
        fig.add_bar(name=name, x=xs, y=ys, base=bases, marker_color=colors[name],
                    text=texts, textposition="outside", cliponaxis=False,
                    hovertext=hovers, hoverinfo="text", textfont=dict(size=12))
    for i in range(len(levels) - 1):  # thin connector lines between bars
        fig.add_shape(type="line", x0=i + 0.4, x1=i + 0.6, y0=levels[i], y1=levels[i],
                      line=dict(color=GRID, width=1))
    fig.update_layout(
        barmode="overlay", bargap=0.12, height=height,
        margin=dict(t=50, b=10, l=10, r=10),
        legend=dict(orientation="h", y=1.08, x=0),
        yaxis=dict(title="CAD", gridcolor=GRID, tickformat="$,.2s", rangemode="tozero",
                   automargin=True),
        xaxis=dict(categoryorder="array", categoryarray=labels, tickangle=0,
                   tickfont=dict(size=12), automargin=True),
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
