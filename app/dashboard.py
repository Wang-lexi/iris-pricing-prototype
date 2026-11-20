"""Streamlit page: pocket price waterfall. Run from the repo root:

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
    check_against_source,
    load_input,
    prepare_input,
    waterfall,
)
from src.visualization import money, waterfall_chart

st.set_page_config(page_title="Pocket Price Waterfall", layout="wide")

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

wf = waterfall(df)
amount = dict(zip(wf["step"], wf["amount_cad"]))
list_rev, pocket, margin = amount["list"], amount["pocket"], amount["margin"]

if list_rev <= 0 or pocket <= 0:
    st.error("List revenue and pocket revenue must be positive to compute percentages.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("List revenue", money(list_rev))
c2.metric("Pocket revenue", money(pocket))
c3.metric("Price leakage", money(list_rev - pocket), f"{1 - pocket / list_rev:.1%} of list",
          delta_color="off")
c4.metric("Pocket margin", money(margin), f"{margin / pocket:.1%} of pocket revenue",
          delta_color="off")

st.plotly_chart(waterfall_chart(wf), width="stretch")

table = wf.assign(
    amount=wf["amount_cad"].map("{:,.0f}".format),
    pct=wf["pct_of_list"].map("{:.2%}".format),
)[["label", "amount", "pct"]]
table.columns = ["Step", "Amount (CAD)", "% of list revenue"]
st.dataframe(table, hide_index=True, width="stretch")

gap = check_against_source(df)
st.caption(
    "Price leakage = list revenue - pocket revenue (discounts and allowances). "
    "Freight, handling and COGS are shown to reach margin but are not counted as leakage."
    + (f" Check: computed invoice revenue differs from source by at most {gap:.4f} CAD."
       if gap is not None else "")
)
