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
from src.regression_charts import actual_vs_predicted_chart, drivers_chart, residual_histogram
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
st.sidebar.header("Model settings")
# Settings are shared with the Root Cause page: keep them when switching pages.
for _key, _default in SHARED_DEFAULTS.items():
    st.session_state.setdefault(_key, _default)
    st.session_state[_key] = st.session_state[_key]
product_level = st.sidebar.radio(
    "Product enters the model as", ["category", "id"], format_func=str.capitalize,
    key="model_product_level",
    help="Category: 5 groups. ID: 50 separate products (more detail, noisier estimates).")
test_share = st.sidebar.slider("Share of latest transactions held out for testing",
                               0.10, 0.40, step=0.05, format="%.2f", key="model_test_share")
top_share = st.sidebar.slider("Flag the top share of residuals", 0.01, 0.20, step=0.01,
                              format="%.2f", key="model_top_share",
                              help="0.05 flags the 5% of transactions with the largest "
                                   "positive residuals.")

result = fit(fp, test_share, product_level)
flagged, threshold = flag_exceptions(result.scored, top_share)

st.sidebar.header("Filters")
st.sidebar.caption("Filters narrow the charts and tables. Model performance is always for "
                   "the whole data set.")
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
st.warning(
    "**Synthetic data, statistical screening only.** This page shows which transactions "
    "received a larger price reduction than the model expects from quantity, customer tier, "
    "product, channel, region and month. A large residual is a reason to look, not proof of "
    "a pricing mistake or of recoverable profit.")
st.markdown(
    "**Jump to:** [1. Model](#model) · [2. Actual vs predicted](#fit) · [3. Drivers](#drivers) · "
    "[4. Exceptions](#exceptions) · [5. Investigate](#investigate)")

# ---------------------------------------------------------------- 1. model
st.header("1. Model performance", anchor="model")
st.caption(
    "Ordinary least squares on the earliest transactions (training period, up to "
    f"{result.cutoff_date.date()}); the latest transactions are the test set, which the model "
    "never saw. Error is in percentage points (pp) of list revenue.")
train, test = result.metrics.set_index("sample").loc["Train"], result.metrics.set_index("sample").loc["Test"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("R² (test)", f"{test['r_squared']:.3f}", f"train {train['r_squared']:.3f}",
          delta_color="off", delta_arrow="off")
c2.metric("MAE (test)", f"{test['mae'] * 100:.2f} pp", f"train {train['mae'] * 100:.2f} pp",
          delta_color="off", delta_arrow="off")
c3.metric("RMSE (test)", f"{test['rmse'] * 100:.2f} pp", f"train {train['rmse'] * 100:.2f} pp",
          delta_color="off", delta_arrow="off")
c4.metric("Observations", f"{int(train['observations']):,} train",
          f"{int(test['observations']):,} test", delta_color="off", delta_arrow="off")
st.markdown(f"**Fitted equation:** `{equation_text(result)}`")
with st.expander("What the model does and does not do"):
    base = baseline_levels(data, product_level)
    st.markdown(
        "- **Dependent variable:** (list revenue - pocket revenue) / list revenue, the same "
        "pocket revenue as the Price Waterfall.\n"
        "- **Predictors:** ln(quantity), month number (a linear trend), and dummy variables "
        "for customer tier, product, sales channel and province. Baselines: "
        + ", ".join(f"{k} = {v}" for k, v in base.items()) + ".\n"
        "- **Not used:** pocket revenue, discount amounts, rebates, allowances, manual price "
        "overrides and approved discount limits. They determine the target or are kept for "
        "the investigation afterwards.\n"
        "- **Month** is a trend rather than 12 dummies because the test months come after the "
        "training months, so month dummies could not be estimated for them.\n"
        "- **Limits:** a linear model on synthetic data; it cannot see deal-specific context "
        "(strategic account, competitive bid, negotiation), so a large residual can be "
        "legitimate. Test R² can differ from train R² just because the test months happen to be "
        "less noisy.")
with st.expander("Data checks"):
    st.dataframe(data_checks(data), hide_index=True, width="stretch")

st.divider()

# ----------------------------------------------------------------- 2. fit
st.header("2. Actual vs predicted reduction rate", anchor="fit")
st.caption("Each dot is a transaction. On the dashed line the reduction is as expected; "
           "above it the transaction received more reduction than the model predicts.")
if view.empty:
    st.warning("No transactions match the current filters.")
    st.stop()
st.plotly_chart(actual_vs_predicted_chart(view), width="stretch")
left, right = st.columns([2, 1])
with left:
    st.markdown("**Residual distribution** (all transactions)")
    st.plotly_chart(residual_histogram(flagged, threshold), width="stretch")
with right:
    st.metric("Residual threshold", pp(threshold),
              f"top {top_share:.0%} of residuals", delta_color="off", delta_arrow="off")
    st.metric("Statistical outliers", f"{int(flagged['statistical_exception'].sum()):,}",
              f"{int(view['statistical_exception'].sum()):,} in current filter",
              delta_color="off", delta_arrow="off")
    st.metric("Contract policy exceptions", f"{int(flagged['policy_exception'].sum()):,}",
              f"{int(view['policy_exception'].sum()):,} in current filter",
              delta_color="off", delta_arrow="off")

st.divider()

# -------------------------------------------------------------- 3. drivers
st.header("3. Regression drivers", anchor="drivers")
st.caption("Effect on the reduction rate in percentage points of list revenue, compared with "
           "the baseline level, other factors held constant. Whiskers are 95% confidence "
           "intervals. Orange raises the reduction, blue lowers it.")
st.plotly_chart(drivers_chart(result.coefficients), width="stretch")
with st.expander("Coefficient table"):
    table = result.coefficients[["label", "coef_pp", "ci_low_pp", "ci_high_pp", "p_value"]].copy()
    table.columns = ["Driver", "Effect (pp)", "CI low (pp)", "CI high (pp)", "p-value"]
    st.dataframe(table, hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(format="%.2f")
                                for c in ["Effect (pp)", "CI low (pp)", "CI high (pp)"]}
                 | {"p-value": st.column_config.NumberColumn(format="%.3f")})
    st.caption("Quantity is the effect of doubling the quantity. Month is the effect of one "
               "month later.")

st.divider()

# ---------------------------------------------------------- 4. exceptions
st.header("4. Potential pricing exceptions", anchor="exceptions")
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
st.header("5. Investigate a transaction", anchor="investigate")
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
