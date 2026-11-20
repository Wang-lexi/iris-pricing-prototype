"""Streamlit page: pocket price waterfall with a four-level drill-down.

    1. Company overview   2. Product   3. Customer vs product   4. Transaction detail

Run from the repo root:

    streamlit run app/dashboard.py
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

from src.pricing_analysis import (
    DATA_PATH,
    add_row_metrics,
    compare_steps,
    leakage_sources,
    load_input,
    waterfall,
)
from src.visualization import compare_chart, money, waterfall_chart

st.set_page_config(page_title="Pocket Price Waterfall", layout="wide")
st.markdown(  # use the full page width
    "<style>.block-container{max-width:100%;padding-left:2.5rem;padding-right:2.5rem;}"
    "</style>", unsafe_allow_html=True)

FILTERS = {
    "Customer tier": "customer_tier",
    "Industry": "industry",
    "Province": "province",
    "Sales channel": "sales_channel",
    "Product category": "product_category",
}

HOW_TO_READ = (
    "**How to read it:** the chart starts at list revenue and steps down. "
    ":orange[Orange bars] are money taken out at each step; the :blue[blue lines] mark "
    "what is left after the discount (invoice revenue) and after all allowances "
    "(pocket revenue); the :green[green bar] is the final pocket margin. "
    "Price leakage = list revenue - pocket revenue; freight, handling and COGS are shown "
    "only to reach margin.")


@st.cache_data
def load(data_fingerprint: str) -> pd.DataFrame:
    """Cached per data file content: a changed CSV can never be served from a stale cache."""
    return add_row_metrics(load_input())


def amounts(wf: pd.DataFrame) -> dict:
    return dict(zip(wf["step"], wf["amount_cad"]))


def kpi_row(wf: pd.DataFrame, ref: pd.DataFrame | None = None, ref_name: str = "") -> None:
    """Four headline numbers; optionally show a reference leakage rate for comparison."""
    a = amounts(wf)
    list_rev, pocket, margin = a["list"], a["pocket"], a["margin"]
    leak_text = f"{1 - pocket / list_rev:.1%} of list" if list_rev else "n/a"
    if ref is not None:
        r = amounts(ref)
        leak_text += f" ({ref_name}: {1 - r['pocket'] / r['list']:.1%})"
    margin_text = f"{margin / pocket:.1%} of pocket revenue" if pocket > 0 else "n/a"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("List revenue", money(list_rev))
    c2.metric("Pocket revenue", money(pocket))
    c3.metric("Price leakage", money(list_rev - pocket), leak_text,
              delta_color="off", delta_arrow="off")
    c4.metric("Pocket margin", money(margin), margin_text,
              delta_color="off", delta_arrow="off")


def waterfall_table(wf: pd.DataFrame) -> None:
    table = wf.assign(
        amount=wf["amount_cad"].map("{:,.0f}".format),
        pct=wf["pct_of_list"].map("{:.2%}".format),
    )[["label", "amount", "pct"]]
    table.columns = ["Step", "Amount (CAD)", "% of list revenue"]
    st.dataframe(table, hide_index=True, width="stretch")


df_all = load(hashlib.md5(DATA_PATH.read_bytes()).hexdigest())

# ---------------------------------------------------------------- sidebar
st.sidebar.header("Filters")
st.sidebar.caption("These narrow the data for all four sections.")
df = df_all
for label, col in FILTERS.items():
    chosen = st.sidebar.multiselect(label, sorted(df_all[col].unique()))
    if chosen:
        df = df[df[col].isin(chosen)]
st.sidebar.caption(f"{len(df):,} of {len(df_all):,} transactions selected")

st.title("Pocket Price Waterfall")
st.caption("Synthetic B2B manufacturing data, CAD, calendar year 2025. "
           "Four steps: 1 Company, 2 Product, 3 Customer, 4 Transaction.")
st.markdown(
    "**Jump to:** [1. Company overview](#1-company-overview) · [2. Product](#2-product) · "
    "[3. Customer vs product](#3-customer-vs-product) · "
    "[4. Transaction detail](#4-transaction-detail)")

if df.empty:
    st.warning("No transactions match the current filters.")
    st.stop()

wf_all = waterfall(df)
if wf_all["amount_cad"].iloc[0] <= 0 or amounts(wf_all)["pocket"] <= 0:
    st.error("List revenue and pocket revenue must be positive.")
    st.stop()

# ---------------------------------------------------- 1. company overview
st.header("1. Company overview")
st.caption("The whole company by default: where does list-price revenue leak away?")
kpi_row(wf_all)
st.plotly_chart(waterfall_chart(wf_all), width="stretch")
st.markdown(HOW_TO_READ)

src = leakage_sources(wf_all)
top = src.iloc[0]
st.success(
    f"**Biggest source of leakage: {top['label']}** — {money(top['amount_cad'])}, "
    f"{top['pct_of_list']:.1%} of list revenue, {top['share_of_leakage']:.0%} of all leakage.")
with st.expander("Leakage sources ranked / waterfall table"):
    ranked = src.assign(
        amount=src["amount_cad"].map("{:,.0f}".format),
        pct=src["pct_of_list"].map("{:.2%}".format),
        share=src["share_of_leakage"].map("{:.1%}".format),
    )[["label", "amount", "pct", "share"]]
    ranked.columns = ["Source", "Amount (CAD)", "% of list revenue", "Share of leakage"]
    st.dataframe(ranked, hide_index=True, width="stretch")
    waterfall_table(wf_all)

st.divider()

# -------------------------------------------------------------- 2. product
st.header("2. Product")
st.caption("Choose a product to analyse only its transactions.")
cat = df.groupby("product_id")["product_category"].first()
product = st.selectbox("Product", sorted(df["product_id"].unique()), index=None,
                       format_func=lambda p: f"{p} · {cat[p]}",
                       placeholder="Choose a product")
customer = None
if product is None:
    st.info("Choose a product above to see its waterfall.")
else:
    df_p = df[df["product_id"] == product]
    wf_p = waterfall(df_p)
    st.caption(f"{len(df_p):,} transactions from {df_p['customer_id'].nunique()} customers.")
    kpi_row(wf_p, wf_all, "company")
    st.plotly_chart(waterfall_chart(wf_p), width="stretch")
    vs_company = compare_steps(wf_p, wf_all)
    worst = vs_company.loc[vs_company["difference_pp"].idxmax()]
    if worst["difference_pp"] > 0:
        st.info(f"Compared with the company, this product gives away more at "
                f"**{worst['label']}** (+{worst['difference_pp']:.2f} percentage points "
                f"of list revenue).")

st.divider()

# ------------------------------------------------------ 3. customer vs product
st.header("3. Customer vs product")
st.caption("Choose a customer who bought this product and compare their price structure "
           "with all customers who bought it.")
if product is None:
    st.info("Choose a product in step 2 first.")
else:
    info = df_p.groupby("customer_id").first()
    customer = st.selectbox(
        "Customer company",
        sorted(info.index, key=lambda c: info.loc[c, "customer_name"]),
        index=None,
        format_func=lambda c: (f"{info.loc[c, 'customer_name']} · {info.loc[c, 'industry']}"
                               f" · {info.loc[c, 'customer_tier']}"),
        placeholder="Choose a customer company", key=f"customer_{product}")
    if customer is None:
        st.info("Choose a customer company above to compare.")
    else:
        prof = info.loc[customer]
        st.markdown(
            f"**{prof['customer_name']}** — **Industry:** {prof['industry']} · "
            f"**Province:** {prof['province']} · **Tier:** {prof['customer_tier']} · "
            f"**Channel:** {prof['sales_channel']} · "
            f"**Customer for:** {prof['relationship_years']} yrs · "
            f"**Annual revenue:** {prof['annual_revenue_band_cad']} CAD · "
            f"**Payment terms:** {prof['payment_terms_days']} days")

        groups = {
            "All other customers of this product": None,
            "Same industry": "industry",
            "Same customer tier": "customer_tier",
            "Same sales channel": "sales_channel",
            "Same province": "province",
        }
        group = st.radio("Compare with", list(groups), horizontal=True,
                         key=f"group_{product}_{customer}")
        col = groups[group]
        others = df_p[df_p["customer_id"] != customer]
        if col is not None:
            others = others[others[col] == prof[col]]
            ref_name = f"other {prof[col]} customers"
        else:
            ref_name = "all other customers"

        df_c = df_p[df_p["customer_id"] == customer]
        wf_c = waterfall(df_c)
        st.caption(f"{len(df_c):,} transaction(s) of this product by this customer. "
                   f"Comparison group: {others['customer_id'].nunique()} other customer(s), "
                   f"{len(others):,} transaction(s).")
        if others.empty:
            st.warning("No other customers match this group for this product. "
                       "Try another comparison group.")
        else:
            wf_o = waterfall(others)
            kpi_row(wf_c, wf_o, ref_name)
            cmp = compare_steps(wf_c, wf_o)
            left, right = st.columns([3, 2])
            with left:
                st.plotly_chart(
                    compare_chart(cmp, prof["customer_name"], ref_name.capitalize()),
                    width="stretch")
            with right:
                tbl = pd.DataFrame({
                    "Step": cmp["label"],
                    "This customer (%)": cmp["selected"] * 100,
                    "Comparison group (%)": cmp["reference"] * 100,
                    "Difference (pp)": cmp["difference_pp"],
                })
                st.dataframe(tbl, hide_index=True, width="stretch",
                             column_config={c: st.column_config.NumberColumn(format="%.2f")
                                            for c in tbl.columns[1:]})
                st.caption("Each step as % of list revenue; pp = percentage points. "
                           "COGS is left out because it is a cost, not a price concession.")
        with st.expander("This customer's full waterfall"):
            st.plotly_chart(waterfall_chart(wf_c, height=480), width="stretch")

st.divider()

# ------------------------------------------------------ 4. transaction detail
st.header("4. Transaction detail")
st.caption("Open a single transaction to see its full waterfall and how it compares with "
           "other transactions of the same product.")
if customer is None:
    st.info("Choose a product and a customer in steps 2 and 3 first.")
else:
    tx = df_c
    view = tx[["transaction_id", "transaction_date", "quantity_units", "list_unit_price_cad",
               "discount_rate", "leakage_rate", "price_override_used",
               "pocket_margin_cad"]].copy()
    view["transaction_date"] = pd.to_datetime(view["transaction_date"]).dt.date
    view["discount_rate"] *= 100
    view["leakage_rate"] *= 100
    st.dataframe(view.rename(columns={"discount_rate": "discount_%",
                                      "leakage_rate": "leakage_%"}),
                 hide_index=True, width="stretch")

    tx_id = st.selectbox("Transaction", list(tx["transaction_id"]), index=0,
                         key=f"tx_{product}_{customer}")
    row = tx[tx["transaction_id"] == tx_id]
    t = row.iloc[0]
    wf_t = waterfall(row)
    kpi_row(wf_t, wf_p, "product avg")
    st.plotly_chart(waterfall_chart(wf_t, height=520), width="stretch")

    pct_lower = (df_p["discount_rate"] < t["discount_rate"]).mean()
    lines = [
        f"On-invoice discount **{t['discount_rate']:.1%}** vs product median "
        f"**{df_p['discount_rate'].median():.1%}** — higher than {pct_lower:.0%} of this "
        f"product's transactions.",
        f"Total leakage **{t['leakage_rate']:.1%}** of list vs product median "
        f"**{df_p['leakage_rate'].median():.1%}**.",
        f"Quantity **{t['quantity_units']:,.0f}** vs product median "
        f"**{df_p['quantity_units'].median():,.0f}**.",
        f"Price override used: **{t['price_override_used']}**.",
    ]
    if t["pocket_margin_cad"] < 0:
        lines.append(":red[Pocket margin is negative on this transaction.]")
    st.markdown("**How this transaction compares with other transactions of this product:**")
    st.markdown("\n".join(f"- {s}" for s in lines))
    st.caption("These are comparisons with peers, not conclusions: a large order can "
               "legitimately earn a bigger discount. Checking against contract terms is "
               "the next step (Model 2).")
