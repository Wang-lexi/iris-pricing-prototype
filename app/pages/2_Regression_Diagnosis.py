"""Streamlit page: Regression Diagnosis (Model 2).

Which transactions got a bigger price reduction than normal business factors explain?
Appears in the sidebar navigation next to the Price Waterfall page:

    streamlit run app/dashboard.py
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from src.pricing_analysis import DATA_PATH, waterfall
from src.regression import (
    CONTRACTS_PATH,
    PREDICTED,
    RESIDUAL,
    STD_RESIDUAL,
    TARGET,
    baseline_levels,
    data_checks,
    equation_text,
    fit_model,
    flag_exceptions,
    load_dataset,
)
from src.regression_charts import actual_vs_predicted_chart
from src.visualization import money, waterfall_chart

st.set_page_config(page_title="Regression Diagnosis", layout="wide")
st.markdown(
    "<style>.block-container{max-width:100%;padding-left:2.5rem;padding-right:2.5rem;}</style>",
    unsafe_allow_html=True)


def _fingerprint() -> str:
    """Changes whenever a data file changes, so a stale cache can never be served."""
    return hashlib.md5(DATA_PATH.read_bytes() + CONTRACTS_PATH.read_bytes()).hexdigest()


@st.cache_data
def load(fingerprint: str) -> pd.DataFrame:
    return load_dataset()


@st.cache_resource
def fit(fingerprint: str, test_share: float, product_level: str):
    return fit_model(load(fingerprint), test_share, product_level)


SHARED_DEFAULTS = {"model_product_level": "category", "model_test_share": 0.20,
                   "model_top_share": 0.05}


def pct(x: float) -> str:
    return f"{x:.1%}"


def pp(x: float) -> str:
    return f"{x * 100:+.1f} pp"


fp = _fingerprint()
data = load(fp)

# ---------------------------------------------------------------- sidebar
st.sidebar.header("Settings")
# Settings are shared with the Root Cause page: keep them when switching pages.
for _key, _default in SHARED_DEFAULTS.items():
    st.session_state.setdefault(_key, _default)
    st.session_state[_key] = st.session_state[_key]
with st.sidebar.expander("Advanced model settings"):
    product_level = st.radio(
        "Product enters the model as", ["category", "id"], format_func=str.capitalize,
        key="model_product_level",
        help="Category: 5 groups. ID: 50 separate products (more detail, noisier estimates).")
    test_share = st.slider("Share of latest transactions held out for testing",
                           0.10, 0.40, step=0.05, format="%.2f", key="model_test_share")
top_share = st.sidebar.slider("Flag the top share of unusual transactions", 0.01, 0.20, step=0.01,
                              format="%.2f", key="model_top_share",
                              help="0.05 flags the 5% of transactions with the largest "
                                   "positive residuals.")

result = fit(fp, test_share, product_level)
flagged, threshold = flag_exceptions(result.scored, top_share)

st.sidebar.header("Filters")
st.sidebar.caption("Filters narrow the charts and tables. The model itself always uses all data.")
customers = flagged.drop_duplicates("customer_id").set_index("customer_id")["customer_name"]
products = flagged.drop_duplicates("product_id").set_index("product_id")["product_category"]
sel_customers = st.sidebar.multiselect(
    "Customer", sorted(customers.index), format_func=lambda c: f"{c} · {customers[c]}")
sel_products = st.sidebar.multiselect(
    "Product", sorted(products.index), format_func=lambda p: f"{p} · {products[p]}")
sel_regions = st.sidebar.multiselect("Region (province)", sorted(flagged["province"].unique()))

view = flagged
if sel_customers:
    view = view[view["customer_id"].isin(sel_customers)]
if sel_products:
    view = view[view["product_id"].isin(sel_products)]
if sel_regions:
    view = view[view["province"].isin(sel_regions)]
st.sidebar.caption(f"{len(view):,} of {len(flagged):,} transactions selected")

# ----------------------------------------------------------------- header
st.title("Regression Diagnosis")
st.info("Synthetic data. A flagged transaction is a reason to look, not proof of a pricing mistake.")
st.markdown(
    "**Jump to:** [1. The model](#model) · [2. Unusual transactions](#fit) · "
    "[3. Exceptions](#exceptions) · [4. Investigate](#investigate)")

# ---------------------------------------------------------------- 1. model
st.header("1. The model", anchor="model")
st.markdown(
    "**The idea:** transactions that look alike should get similar price reductions. We predict "
    "the reduction each transaction *should* get from normal business factors, then look at the "
    "ones that got much more.")
st.latex(r"y = \beta_0 + \beta_1 x_1 + \beta_2 x_2 + \beta_3 x_3 + \beta_4 x_4 "
         r"+ \beta_5 x_5 + \beta_6 x_6 + \varepsilon")
st.markdown(
    "| Symbol | Variable | What it means |\n|---|---|---|\n"
    "| **y** | Price reduction rate | (List revenue - Pocket revenue) / List revenue: the share of the "
    "list price given away through discounts, rebates and allowances. This is what we predict. |\n"
    "| **x₁** | Quantity | Units bought (in log form). Bigger orders usually earn bigger discounts. |\n"
    "| **x₂** | Customer tier | Small, Mid-Market, Large or Strategic. Bigger customers negotiate more. |\n"
    "| **x₃** | Product | Product category. Different product lines carry different margins. |\n"
    "| **x₄** | Sales channel | Direct or Distributor. |\n"
    "| **x₅** | Province | Where the customer is located. |\n"
    "| **x₆** | Month | Month of the sale: a drift in discounts over the year. |\n"
    "| **β₀ ... β₆** | Effects | How much each variable moves the reduction. The model learns them "
    "from the data (ordinary least squares). |\n"
    "| **ε** | Residual | What the model cannot explain: **actual minus predicted**. A large "
    "positive ε means more reduction than normal, so we look at it. |")
with st.expander("Model details: accuracy, coefficients, assumptions"):
    metrics = result.metrics.set_index("sample")
    st.markdown(
        f"Fitted on the earliest transactions (up to {result.cutoff_date.date()}) and tested on "
        "the latest ones, which the model never saw.")
    st.dataframe(pd.DataFrame({
        "Sample": metrics.index, "Transactions": metrics["observations"].astype(int).values,
        "R²": metrics["r_squared"].values, "MAE (pp)": metrics["mae"].values * 100,
        "RMSE (pp)": metrics["rmse"].values * 100}),
        hide_index=True, width="stretch",
        column_config={"R²": st.column_config.NumberColumn(format="%.3f"),
                       "MAE (pp)": st.column_config.NumberColumn(format="%.2f"),
                       "RMSE (pp)": st.column_config.NumberColumn(format="%.2f")})
    st.markdown(f"**Fitted equation:** `{equation_text(result)}`")
    table = result.coefficients[["label", "coef_pp", "ci_low_pp", "ci_high_pp", "p_value"]].copy()
    table.columns = ["Driver", "Effect (pp)", "CI low (pp)", "CI high (pp)", "p-value"]
    st.dataframe(table, hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(format="%.2f")
                                for c in ["Effect (pp)", "CI low (pp)", "CI high (pp)"]}
                 | {"p-value": st.column_config.NumberColumn(format="%.3f")})
    base = baseline_levels(data, product_level)
    st.markdown(
        "- Each effect is in percentage points of list revenue, against a baseline: "
        + ", ".join(f"{k} = {v}" for k, v in base.items()) + ". Quantity is the effect of "
        "doubling the order; month is the effect of one month later.\n"
        "- **Not used as predictors:** pocket revenue, discount amounts, rebates, allowances, "
        "manual price overrides and approved discount limits. They build the target or are kept "
        "for the investigation afterwards.\n"
        "- **Limits:** a linear model on synthetic data. It cannot see deal context "
        "(negotiation, competitive bids), so a large residual can be legitimate.")
    st.markdown("**Data checks**")
    st.dataframe(data_checks(data), hide_index=True, width="stretch")

st.divider()

# ----------------------------------------------------------------- 2. fit
st.header("2. Which transactions got more than expected?", anchor="fit")
st.caption("Each dot is one transaction. Dots on the dashed line got the reduction the model "
           "expects; dots well above it got more.")
if view.empty:
    st.warning("No transactions match the current filters.")
    st.stop()
st.plotly_chart(actual_vs_predicted_chart(view), width="stretch")
st.markdown(
    f":orange[**{int(view['statistical_exception'].sum()):,} transactions**] are unusually high "
    f"(the top {top_share:.0%} of residuals). "
    f":red[**{int(view['policy_exception'].sum()):,}**] have an on-invoice discount above their "
    "contract limit. Both checks are independent.")

st.divider()

# ---------------------------------------------------------- 4. exceptions
st.header("3. Potential pricing exceptions", anchor="exceptions")
st.caption("Statistical outliers are transactions with a residual above the threshold. "
           "Contract policy exceptions are transactions whose on-invoice discount is above "
           "the contract's approved limit. The two checks are independent.")
show = st.radio("Show", ["Either", "Statistical outliers", "Contract policy exceptions"],
                horizontal=True)
mask = {"Either": view["any_exception"],
        "Statistical outliers": view["statistical_exception"],
        "Contract policy exceptions": view["policy_exception"]}[show]
exceptions = view[mask].sort_values(RESIDUAL, ascending=False)
st.caption(f"{len(exceptions):,} transactions, largest residual first.")

if exceptions.empty:
    st.info("No exceptions in the current selection.")
else:
    out = pd.DataFrame({
        "Transaction ID": exceptions["transaction_id"],
        "Customer": exceptions["customer_name"],
        "Product": exceptions["product_id"] + " · " + exceptions["product_category"],
        "Region": exceptions["province"],
        "Actual reduction %": exceptions[TARGET] * 100,
        "Predicted reduction %": exceptions[PREDICTED] * 100,
        "Residual (pp)": exceptions[RESIDUAL] * 100,
        "Statistical outlier": exceptions["statistical_exception"].map({True: "Yes", False: "No"}),
        "Contract policy exception": exceptions["policy_exception"].map({True: "Yes", False: "No"}),
        "Sample": exceptions["sample"],
    })
    fmt = st.column_config.NumberColumn(format="%.1f")
    st.dataframe(out, hide_index=True, width="stretch", height=360,
                 column_config={"Actual reduction %": fmt, "Predicted reduction %": fmt,
                                "Residual (pp)": st.column_config.NumberColumn(format="%+.1f")})
    st.download_button("Download this table (CSV)", out.to_csv(index=False).encode(),
                       "pricing_exceptions.csv", "text/csv")

st.divider()

# --------------------------------------------------------- 5. investigate
st.header("4. Investigate a transaction", anchor="investigate")
st.caption("Choose a transaction from the table above to see how far it is from the model's "
           "expectation and its Price Waterfall.")
if exceptions.empty:
    st.info("No transaction to investigate in the current selection.")
    st.stop()

by_id = exceptions.set_index("transaction_id")
tx_id = st.selectbox(
    "Transaction", list(by_id.index), index=None, placeholder="Choose a transaction",
    format_func=lambda t: (f"{t} · {by_id.loc[t, 'customer_name']} · "
                           f"residual {by_id.loc[t, RESIDUAL] * 100:+.1f} pp"
                           f"{' · over contract limit' if by_id.loc[t, 'policy_exception'] else ''}"))
if tx_id is None:
    st.info("Choose a transaction above.")
    st.stop()

row = data[data["transaction_id"] == tx_id]
t = by_id.loc[tx_id]
st.markdown(
    f"**{t['customer_name']}** — **Product:** {t['product_id']} · {t['product_category']} · "
    f"**Tier:** {t['customer_tier']} · **Channel:** {t['sales_channel']} · "
    f"**Province:** {t['province']} · **Date:** {pd.to_datetime(t['transaction_date']).date()} · "
    f"**Quantity:** {t['quantity_units']:,.0f}")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Actual reduction", pct(t[TARGET]))
m2.metric("Predicted reduction", pct(t[PREDICTED]))
m3.metric("Residual", pp(t[RESIDUAL]), f"{t[STD_RESIDUAL]:+.1f} model standard errors",
          delta_color="off", delta_arrow="off")
m4.metric("Pocket margin", money(t["pocket_margin_cad"]))

limit = t["approved_max_on_invoice_discount_rate"]
notes = [f"On-invoice discount **{pct(t['discount_rate'])}** of list revenue vs the contract's "
         f"approved maximum **{pct(limit)}**"
         + (f" — :red[**{t['excess_discount_pp']:.1f} pp above the limit**]." if t["policy_exception"]
            else " — within the limit."),
         f"Manual price override used: **{t['price_override_used']}** (shown for the "
         "investigation; the model does not use it).",
         f"This transaction is in the **{t['sample'].lower()}** sample."]
if t["pocket_margin_cad"] < 0:
    notes.append(":red[Pocket margin is negative.]")
st.markdown("\n".join(f"- {n}" for n in notes))

st.markdown("**Price Waterfall for this transaction** (same calculation as the Waterfall page)")
st.plotly_chart(waterfall_chart(waterfall(row), height=520), width="stretch")
st.page_link("dashboard.py", label="Open the full Price Waterfall page")
st.caption("A residual says the discount is unusual compared with similar transactions, "
           "not that it was wrong. Check the deal context before drawing a conclusion.")
