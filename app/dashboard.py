"""Streamlit page: pocket price waterfall with a four-level drill-down.

    1. Company overview   2. Product   3. Customer vs product   4. Single transaction

Run from the repo root:

    streamlit run app/dashboard.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

from src.preprocessing import classify_tables, integrate
from src.pricing_analysis import (
    DATA_PATH,
    OPTIONAL_ZERO_COLS,
    REQUIRED_COLS,
    add_row_metrics,
    check_against_source,
    compare_steps,
    leakage_sources,
    load_input,
    prepare_input,
    waterfall,
)
from src.visualization import compare_chart, money, waterfall_chart

st.set_page_config(page_title="Pocket Price Waterfall", layout="wide")
st.markdown(
    "<style>.block-container{max-width:100%;padding-left:2.5rem;padding-right:2.5rem;}"
    "</style>", unsafe_allow_html=True)

FILTERS = {
    "Customer tier": "customer_tier",
    "Industry": "industry",
    "Province": "province",
    "Sales channel": "sales_channel",
    "Product category": "product_category",
}


@st.cache_data
def load_sample() -> pd.DataFrame:
    return load_input()


def load_uploaded(files) -> tuple[pd.DataFrame, list[str]]:
    """Read uploaded CSVs, recognise them by columns, integrate, validate."""
    tables = {f.name: pd.read_csv(f) for f in files}
    roles = classify_tables(tables)
    if not roles:
        raise ValueError("None of the uploaded files was recognised. Check the column names "
                         "under 'Required format'.")
    notes = [f"Recognised: {', '.join(sorted(roles))}."]
    df, more = prepare_input(integrate(roles))
    return df, notes + more


def step_amounts(wf: pd.DataFrame) -> dict:
    return dict(zip(wf["step"], wf["amount_cad"]))


def kpi_row(wf: pd.DataFrame, ref: pd.DataFrame | None = None, ref_name: str = "") -> None:
    """Four headline numbers; optionally compare the leakage rate with a reference."""
    a = step_amounts(wf)
    list_rev, pocket, margin = a["list"], a["pocket"], a["margin"]
    leak = 1 - pocket / list_rev if list_rev else float("nan")
    leak_text = f"{leak:.1%} of list"
    if ref is not None:
        r = step_amounts(ref)
        ref_leak = 1 - r["pocket"] / r["list"]
        leak_text += f" ({ref_name}: {ref_leak:.1%})"
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


COLOR_KEY = ("**How to read the chart:** :blue[blue bars] = money left after each step "
             "(running total); :orange[orange bars] = money taken out at that step; "
             ":green[green bar] = final pocket margin.")

# ------------------------------------------------------------ data source
st.sidebar.header("Data")
source = st.sidebar.radio("Source", ["Sample data (synthetic)", "Upload your own"])

notes: list[str] = []
if source == "Upload your own":
    files = st.sidebar.file_uploader(
        "CSV file(s)", type="csv", accept_multiple_files=True,
        help="One integrated file, or separate transactions + adjustments (+ customers, "
             "products) files. Tables are recognised by their columns.")
    with st.sidebar.expander("Required format"):
        st.markdown(
            "**Required columns:** " + ", ".join(f"`{c}`" for c in REQUIRED_COLS) + "\n\n"
            "**Optional (blank or missing = 0):** "
            + ", ".join(f"`{c}`" for c in OPTIONAL_ZERO_COLS) + "\n\n"
            "**For filters:** `customer_tier`, `industry`, `province`, `sales_channel`, "
            "`product_category`.\n\n"
            "**For the drill-down:** `product_id`, `customer_id`, `transaction_id`.\n\n"
            "If you upload separate files, include `transaction_id` in transactions and "
            "adjustments, and `customer_id` / `product_id` to attach attributes.")
        st.download_button("Download the sample file", DATA_PATH.read_bytes(),
                           file_name="sample_waterfall_input.csv", mime="text/csv")
    if not files:
        st.title("Pocket Price Waterfall")
        st.info("Upload a CSV in the sidebar to see its waterfall, "
                "or switch to the sample data.")
        st.stop()
    try:
        df_all, notes = load_uploaded(files)
    except Exception as e:  # show a readable message instead of a traceback
        st.title("Pocket Price Waterfall")
        st.error(f"Could not use the uploaded data: {e}")
        st.stop()
    caption = f"Uploaded data: {len(df_all):,} rows."
else:
    df_all = load_sample()
    caption = "Synthetic B2B manufacturing data, CAD, calendar year 2025."

# ---------------------------------------------------------------- filters
st.sidebar.header("Filters")
st.sidebar.caption("These narrow the data for every section on the page.")
df = df_all
available = {label: col for label, col in FILTERS.items() if col in df_all.columns}
for label, col in available.items():
    chosen = st.sidebar.multiselect(label, sorted(df_all[col].dropna().unique()))
    if chosen:
        df = df[df[col].isin(chosen)]
if not available:
    st.sidebar.caption("No filterable columns in this data.")
st.sidebar.caption(f"{len(df):,} of {len(df_all):,} rows selected")

# ------------------------------------------------------------------- page
st.title("Pocket Price Waterfall")
st.caption(caption)
for n in notes:
    st.info(n)

if df.empty:
    st.warning("No rows match the current filters.")
    st.stop()

df = add_row_metrics(df)
wf_all = waterfall(df)
a = step_amounts(wf_all)
if a["list"] <= 0 or a["pocket"] <= 0:
    st.error("List revenue and pocket revenue must be positive to compute percentages.")
    st.stop()

# ---------------------------------------------------- 1. company overview
st.header("1. Company overview")
st.caption("The whole company by default (or whatever the sidebar filters select): "
           "where does list-price revenue leak away?")
kpi_row(wf_all)
st.plotly_chart(waterfall_chart(wf_all), width="stretch")
st.caption(COLOR_KEY + " Leakage = list revenue minus pocket revenue (discounts and "
           "allowances). Freight, handling and COGS are shown to reach margin but are "
           "not counted as leakage.")

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
gap = check_against_source(df)
if gap is not None:
    st.caption(f"Check: computed invoice revenue differs from the source column by at "
               f"most {gap:.4f} CAD.")

st.divider()

# -------------------------------------------------------------- 2. product
st.header("2. Product")
st.caption("Pick one product to analyse only its transactions.")
needs = [c for c in ("product_id", "customer_id") if c not in df.columns]
if needs:
    st.info(f"The drill-down needs column(s) {', '.join(needs)}; they are not in this data.")
    st.stop()

if "product_category" in df.columns:
    cat = df.groupby("product_id")["product_category"].first()
    prod_label = lambda p: f"{p} · {cat[p]}"  # noqa: E731
else:
    prod_label = str
product = st.selectbox("Product", sorted(df["product_id"].unique()), index=None,
                       format_func=prod_label, placeholder="Choose a product")
if product is None:
    st.stop()

df_p = df[df["product_id"] == product]
wf_p = waterfall(df_p)
st.caption(f"{len(df_p):,} transactions from {df_p['customer_id'].nunique()} customers.")
kpi_row(wf_p, wf_all, "company")
st.plotly_chart(waterfall_chart(wf_p), width="stretch")
cmp_company = compare_steps(wf_p, wf_all)
worst = cmp_company.loc[cmp_company["difference_pp"].idxmax()]
if worst["difference_pp"] > 0:
    st.info(f"Compared with the company, this product gives away more at "
            f"**{worst['label']}** (+{worst['difference_pp']:.2f} percentage points of "
            f"list revenue).")

st.divider()

# ------------------------------------------------------ 3. customer vs product
st.header("3. Customer vs product")
st.caption("Pick a customer who bought this product and compare their price structure "
           "with all customers who bought it.")
cust_info = df_p.groupby("customer_id").first()
extras = [c for c in ("customer_tier", "industry") if c in cust_info.columns]
cust_label = lambda c: " · ".join([c] + [str(cust_info.loc[c, e]) for e in extras])  # noqa: E731
customer = st.selectbox("Customer", sorted(df_p["customer_id"].unique()), index=None,
                        format_func=cust_label, placeholder="Choose a customer",
                        key=f"customer_{product}")
if customer is None:
    st.stop()

df_c = df_p[df_p["customer_id"] == customer]
wf_c = waterfall(df_c)
st.caption(f"{len(df_c):,} transaction(s) of this product by this customer.")
kpi_row(wf_c, wf_p, "all customers")
cmp = compare_steps(wf_c, wf_p)
left, right = st.columns([3, 2])
with left:
    st.plotly_chart(compare_chart(cmp, f"Customer {customer}", "All customers (this product)"),
                    width="stretch")
with right:
    tbl = cmp.assign(
        a=cmp["selected"] * 100, b=cmp["reference"] * 100, d=cmp["difference_pp"])[
        ["label", "a", "b", "d"]]
    tbl.columns = ["Step", f"{customer} (%)", "All customers (%)", "Difference (pp)"]
    st.dataframe(tbl, hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(format="%.2f")
                                for c in tbl.columns[1:]})
    st.caption("Each step as % of list revenue. pp = percentage points.")
with st.expander("This customer's waterfall"):
    st.plotly_chart(waterfall_chart(wf_c, height=480), width="stretch")

st.divider()

# ------------------------------------------------------ 4. transaction detail
st.header("4. Transaction detail")
st.caption("Open a single transaction to see its full waterfall and how it compares "
           "with other transactions of the same product.")
tx = df_c.copy()
id_col = "transaction_id" if "transaction_id" in tx.columns else None
if id_col is None:
    tx["transaction_id"] = tx.index.astype(str)
    id_col = "transaction_id"
show_cols = [c for c in (id_col, "transaction_date", "quantity_units", "list_unit_price_cad",
                         "discount_rate", "leakage_rate", "price_override_used",
                         "pocket_margin_cad") if c in tx.columns]
view = tx[show_cols].copy()
for c in ("discount_rate", "leakage_rate"):
    view[c] = view[c] * 100
if "transaction_date" in view.columns:
    view["transaction_date"] = pd.to_datetime(view["transaction_date"]).dt.date
st.dataframe(view.rename(columns={
    "discount_rate": "discount_%", "leakage_rate": "leakage_%"}),
    hide_index=True, width="stretch")

tx_id = st.selectbox("Transaction", list(tx[id_col]), index=0, key=f"tx_{product}_{customer}")
row = tx[tx[id_col] == tx_id]
wf_t = waterfall(row)
t = row.iloc[0]
kpi_row(wf_t, wf_p, "product avg")
st.plotly_chart(waterfall_chart(wf_t, height=520), width="stretch")

peers = df_p
pct_lower = (peers["discount_rate"] < t["discount_rate"]).mean()
st.markdown("**How this transaction compares with other transactions of this product:**")
lines = [
    f"On-invoice discount **{t['discount_rate']:.1%}** vs product median "
    f"**{peers['discount_rate'].median():.1%}** — higher than {pct_lower:.0%} of this "
    f"product's transactions.",
    f"Total leakage **{t['leakage_rate']:.1%}** of list vs product median "
    f"**{peers['leakage_rate'].median():.1%}**.",
    f"Quantity **{t['quantity_units']:,.0f}** vs product median "
    f"**{peers['quantity_units'].median():,.0f}**.",
]
if "price_override_used" in row.columns:
    lines.append("Price override used: **" + str(t["price_override_used"]) + "**.")
if t["pocket_margin_cad"] < 0:
    lines.append(":red[Pocket margin is negative on this transaction.]")
st.markdown("\n".join(f"- {s}" for s in lines))
st.caption("These are comparisons with peers, not conclusions: a large order can "
           "legitimately earn a bigger discount. Checking against contract terms is the "
           "next step (Model 2).")
