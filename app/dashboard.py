"""Streamlit dashboard. Run from the repo root:

    streamlit run app/dashboard.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

from src.preprocessing import load_transactions
from src.pricing_analysis import (
    DEDUCTIONS,
    add_waterfall_columns,
    check_waterfall,
    segment_summary,
    waterfall_totals,
    whale_curve,
)
from src.visualization import leakage_stack_chart, waterfall_chart, whale_chart

st.set_page_config(page_title="Iris Pricing Prototype", layout="wide")

DIMENSIONS = {
    "Customer tier": "customer_tier",
    "Industry": "industry",
    "Province": "province",
    "Sales channel": "sales_channel",
    "Product category": "product_category",
    "Product differentiation": "product_differentiation",
    "Sales rep": "sales_rep_id",
    "Month": "month",
}


@st.cache_data
def load_data() -> pd.DataFrame:
    return add_waterfall_columns(load_transactions())


def money(x: float) -> str:
    return f"${x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"${x:,.0f}"


df_all = load_data()

# ---------------------------------------------------------------- sidebar
st.sidebar.header("Filters")
df = df_all
for label, col in list(DIMENSIONS.items())[:-1]:
    options = sorted(df_all[col].unique())
    chosen = st.sidebar.multiselect(label, options)
    if chosen:
        df = df[df[col].isin(chosen)]
st.sidebar.caption(f"{len(df):,} of {len(df_all):,} transactions selected")

st.title("Price Leakage: Pocket Price Waterfall")
st.caption("Synthetic B2B manufacturing data (CAD), calendar year 2025. Model 1 of 3.")

if df.empty:
    st.warning("No transactions match the current filters.")
    st.stop()

wf = waterfall_totals(df)
get = lambda step: wf.loc[wf["step"] == step, "amount_cad"].iloc[0]  # noqa: E731
list_rev, pocket, margin = get("list"), get("pocket"), get("margin")

k1, k2, k3, k4 = st.columns(4)
k1.metric("List revenue", money(list_rev))
k2.metric("Pocket revenue", money(pocket))
k3.metric("Total leakage", money(list_rev - pocket), f"{1 - pocket / list_rev:.1%} of list",
          delta_color="off")
k4.metric("Pocket margin", money(margin), f"{margin / pocket:.1%} of pocket revenue",
          delta_color="off")

tab1, tab2, tab3, tab4 = st.tabs(
    ["Waterfall", "By segment", "Customer whale curve", "Method & checks"]
)

with tab1:
    st.plotly_chart(waterfall_chart(wf), width='stretch')
    show = wf.assign(
        amount=wf["amount_cad"].map(lambda x: f"{x:,.0f}"),
        pct_of_list=wf["pct_of_list"].map("{:.2%}".format),
    )[["label", "amount", "pct_of_list"]]
    show.columns = ["Step", "Amount (CAD)", "% of list revenue"]
    st.dataframe(show, hide_index=True, width='stretch')

with tab2:
    dim_label = st.selectbox("Break down by", list(DIMENSIONS))
    by = DIMENSIONS[dim_label]
    seg = segment_summary(df, by)
    if by == "month":
        seg = seg.sort_values("month")
    st.plotly_chart(leakage_stack_chart(seg, by), width='stretch')

    table = seg[[by, "n_transactions", "list_revenue_cad", "total_leakage_rate",
                 "invoice_leakage_rate", "off_invoice_leakage_rate", "leakage_cad",
                 "pocket_margin_pct"]].rename(columns={
        by: dim_label, "n_transactions": "Transactions",
        "list_revenue_cad": "List revenue", "total_leakage_rate": "Total leakage %",
        "invoice_leakage_rate": "On-invoice %", "off_invoice_leakage_rate": "Off-invoice %",
        "leakage_cad": "Leakage (CAD)", "pocket_margin_pct": "Pocket margin %"})
    pct_cols = ["Total leakage %", "On-invoice %", "Off-invoice %", "Pocket margin %"]
    table[pct_cols] = table[pct_cols] * 100  # show as percentage points
    st.dataframe(
        table, hide_index=True, width='stretch',
        column_config={
            "List revenue": st.column_config.NumberColumn(format="dollar"),
            "Leakage (CAD)": st.column_config.NumberColumn(format="dollar"),
            **{c: st.column_config.NumberColumn(format="%.2f") for c in pct_cols},
        },
    )
    st.caption("Rates are ratios of sums (leakage CAD / list revenue CAD), "
               "so large orders weigh more than small ones.")

with tab3:
    w = whale_curve(df)
    st.plotly_chart(whale_chart(w), width='stretch')
    losers = w[w["pocket_margin_cad"] < 0]
    st.write(f"**{len(losers)} of {len(w)} customers** have negative pocket margin "
             f"(total {money(losers['pocket_margin_cad'].sum())}). "
             f"Peak of the curve: {w['cum_margin_pct'].max():.0%} of total pocket margin.")
    st.dataframe(
        w[["customer_id", "pocket_margin_cad"]].tail(10).rename(
            columns={"customer_id": "Customer", "pocket_margin_cad": "Pocket margin (CAD)"}),
        hide_index=True, width='stretch')
    st.caption("Ten lowest-margin customers.")

with tab4:
    st.markdown(
        """
**Definitions (per transaction line, CAD)**

- Invoice revenue = List revenue − On-invoice discount
- Pocket revenue = Invoice revenue − Volume rebate − Early payment discount
  − Credit allowance − Promotional allowance
- Pocket margin = Pocket revenue − Cost to serve (freight + handling) − COGS

**Aggregation:** every rate is a ratio of sums, e.g. leakage rate of a step =
Σ step ÷ Σ list revenue. A group's waterfall always adds up to the total.
        """
    )
    checks = check_waterfall(df)
    c1, c2 = st.columns(2)
    c1.metric("Max gap: computed vs source invoice revenue (CAD)",
              f"{checks['invoice_revenue_vs_source']:.4f}")
    c2.metric("Max gap: waterfall identity (CAD)",
              f"{checks['list_minus_all_steps_vs_margin']:.4f}")
    st.caption("Both should be ~0. Note: `invoice_id` in the source data does not "
               "identify a single customer (two transactions share each ID), so it is "
               "not used for grouping.")
