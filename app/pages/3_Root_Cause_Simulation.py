"""Streamlit page: Root Cause and What-If (Model 3).

Pick an unusual transaction, see which deduction caused its big discount, then try a lower
discount and compare pocket revenue and pocket margin with what actually happened.

    streamlit run app/dashboard.py
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from src.diagnosis import (
    COST_TO_SERVE,
    SCOPES,
    baseline_assumptions,
    component_table,
    expected_discount_rate,
    narrative,
    peer_rates,
    portfolio_scenario,
    simulate_frame,
)
from src.diagnosis_charts import comparison_chart, component_excess_chart
from src.pricing_analysis import COGS, DATA_PATH, DISCOUNT, LIST, OFF_INVOICE, waterfall
from src.regression import (
    CONTRACTS_PATH,
    PREDICTED,
    RESIDUAL,
    TARGET,
    fit_model,
    flag_exceptions,
    load_dataset,
)
from src.visualization import money, waterfall_chart

st.set_page_config(page_title="Root Cause & What-If", layout="wide")
st.markdown(
    "<style>.block-container{max-width:100%;padding-left:2.5rem;padding-right:2.5rem;}</style>",
    unsafe_allow_html=True)

SHARED_DEFAULTS = {"model_product_level": "category", "model_test_share": 0.20,
                   "model_top_share": 0.05}
SCOPE_LABELS = {
    "Contract limit exceeded": "Cap discounts at the contract limit",
    "Statistical anomaly": "Close part of the gap to the expected reduction",
    "Either": "Both (take the larger cut for each transaction)",
}


@st.cache_data
def load(fingerprint: str) -> pd.DataFrame:
    return load_dataset()


@st.cache_resource
def fit(fingerprint: str, test_share: float, product_level: str):
    return fit_model(load(fingerprint), test_share, product_level)


def pct(x: float) -> str:
    return f"{x:.1%}"


fp = hashlib.md5(DATA_PATH.read_bytes() + CONTRACTS_PATH.read_bytes()).hexdigest()
data = load(fp)

# ---------------------------------------------------------------- sidebar
st.sidebar.header("Settings")
st.sidebar.caption("Shared with the Regression Diagnosis page, so both pages flag the same "
                   "transactions.")
for key, default in SHARED_DEFAULTS.items():
    st.session_state.setdefault(key, default)
    st.session_state[key] = st.session_state[key]
with st.sidebar.expander("Advanced model settings"):
    product_level = st.radio("Product enters the model as", ["category", "id"],
                             format_func=str.capitalize, key="model_product_level")
    test_share = st.slider("Share of latest transactions held out for testing",
                           0.10, 0.40, step=0.05, format="%.2f", key="model_test_share")
top_share = st.sidebar.slider("Flag the top share of unusual transactions", 0.01, 0.20, step=0.01,
                              format="%.2f", key="model_top_share")

result = fit(fp, test_share, product_level)
flagged, threshold = flag_exceptions(result.scored, top_share)
peers = peer_rates(flagged)

st.sidebar.header("Filters")
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
st.title("Root Cause and What-If")
st.markdown(
    "**Three steps:** ① pick an unusual transaction · ② see what caused its big discount · "
    "③ try a lower discount and compare the profit.")
st.caption("Synthetic data. The what-if results are illustrations, not money the company "
           "would certainly recover.")
st.markdown(
    "**Jump to:** [1. Pick](#choose) · [2. Cause](#cause) · [3. What if](#simulate) · "
    "[4. All unusual transactions](#portfolio)")
if view.empty:
    st.warning("No transactions match the current filters.")
    st.stop()

# ----------------------------------------------------------------- 1. choose
st.header("1. Pick an unusual transaction", anchor="choose")
candidates = view[view["any_exception"]].sort_values(RESIDUAL, ascending=False)
st.caption(
    f"{len(candidates):,} transactions got a bigger price reduction than similar ones, or a "
    "discount above their contract limit. The largest gap is first. There may be a good reason "
    "for each, so treat them as questions to ask, not mistakes.")
if candidates.empty:
    st.info("No unusual transactions in the current selection.")
    st.stop()

st.dataframe(pd.DataFrame({
    "Transaction ID": candidates["transaction_id"],
    "Customer": candidates["customer_name"],
    "Product": candidates["product_id"] + " · " + candidates["product_category"],
    "Region": candidates["province"],
    "Actual reduction %": candidates[TARGET] * 100,
    "Expected reduction %": candidates[PREDICTED] * 100,
    "Above contract limit": candidates["policy_exception"].map({True: "Yes", False: "No"}),
}), hide_index=True, width="stretch", height=260,
    column_config={"Actual reduction %": st.column_config.NumberColumn(format="%.1f"),
                   "Expected reduction %": st.column_config.NumberColumn(format="%.1f")})

by_id = candidates.set_index("transaction_id")
tx_id = st.selectbox(
    "Transaction", list(by_id.index), index=None, placeholder="Choose a transaction",
    format_func=lambda t: (f"{t} · {by_id.loc[t, 'customer_name']} · "
                           f"actual {by_id.loc[t, TARGET]:.1%} vs expected "
                           f"{by_id.loc[t, PREDICTED]:.1%}"))
if tx_id is None:
    st.info("Choose a transaction above.")
    st.stop()

row_df = flagged[flagged["transaction_id"] == tx_id]
row = row_df.iloc[0]
st.markdown(
    f"**{row['customer_name']}** — **Product:** {row['product_id']} · {row['product_category']} · "
    f"**Tier:** {row['customer_tier']} · **Channel:** {row['sales_channel']} · "
    f"**Province:** {row['province']} · **Date:** {row['transaction_date'].date()} · "
    f"**Quantity:** {row['quantity_units']:,.0f}")

st.divider()

# ----------------------------------------------------------------- 2. cause
st.header("2. What caused the big reduction?", anchor="cause")
table = component_table(row, peers)
left, right = st.columns([3, 2])
with left:
    st.caption(f"Each deduction compared with what similar {row['customer_tier']} customers "
               "typically get. Orange bars are above typical, blue below.")
    st.plotly_chart(component_excess_chart(table), width="stretch")
with right:
    st.markdown("\n".join(f"- {n}" for n in narrative(row, table)))
with st.expander("Show the numbers"):
    shown = table[["component", "amount_cad", "pct_of_list", "peer_median_pct", "excess_pp"]].copy()
    shown.columns = ["Deduction", "Amount (CAD)", "% of list price", "Typical for tier %",
                     "Above typical (pp)"]
    st.dataframe(shown, hide_index=True, width="stretch",
                 column_config={"Amount (CAD)": st.column_config.NumberColumn(format="%.0f"),
                                "% of list price": st.column_config.NumberColumn(format="%.2f"),
                                "Typical for tier %": st.column_config.NumberColumn(format="%.2f"),
                                "Above typical (pp)": st.column_config.NumberColumn(format="%+.2f")})
    st.caption("The five deductions add up to list revenue minus pocket revenue, so nothing is "
               "counted twice.")

st.divider()

# -------------------------------------------------------------- 3. what if
st.header("3. What if the discount were lower?", anchor="simulate")
st.markdown("Move the slider or click a quick option, then compare with what actually happened.")

base = baseline_assumptions(row_df)
orig = {"disc": float(base["discount_rate"].iloc[0] * 100),
        "rebate": float(base["rebate_rate"].iloc[0] * 100),
        "early": float(base["early_rate"].iloc[0] * 100),
        "credit": float(base["credit_cad"].iloc[0]),
        "promo": float(base["promo_cad"].iloc[0])}
k = {name: f"{tx_id}_{name}" for name in orig}
for name, value in orig.items():
    st.session_state.setdefault(k[name], value)


def apply(values: dict) -> None:
    for name, value in values.items():
        st.session_state[k[name]] = value


limit_pct = float(row["approved_max_on_invoice_discount_rate"] * 100)
peer_pct = float(peers.loc[row["customer_tier"], DISCOUNT] * 100)
expected_pct = expected_discount_rate(row) * 100

b1, b2, b3, b4 = st.columns(4)
b1.button("Reset to original", on_click=apply, args=(orig,), width="stretch")
b2.button(f"Cap at contract limit ({limit_pct:.1f}%)", width="stretch", on_click=apply,
          args=({"disc": min(orig["disc"], limit_pct)},),
          help="The maximum on-invoice discount this customer's contract approves.")
b3.button(f"Typical for {row['customer_tier']} customers ({peer_pct:.1f}%)", width="stretch",
          on_click=apply, args=({"disc": min(orig["disc"], peer_pct)},),
          help="The median discount of customers in the same tier.")
b4.button(f"Back to expected level ({expected_pct:.1f}%)", width="stretch", on_click=apply,
          args=({"disc": expected_pct},),
          help="The discount at which the total price reduction equals what the model expects.")

disc = st.slider("On-invoice discount (% of list price)", 0.0, max(40.0, orig["disc"] + 5), step=0.1,
                 key=k["disc"], format="%.1f%%")
with st.expander("More assumptions: rebate, early payment, credit, promotion"):
    s1, s2, s3, s4 = st.columns(4)
    rebate = s1.slider("Volume rebate (% of invoice)", 0.0, max(10.0, orig["rebate"] * 1.5),
                       step=0.05, key=k["rebate"], format="%.2f%%")
    early = s2.slider("Early-payment discount (% of invoice)", 0.0, max(5.0, orig["early"] * 1.5),
                      step=0.05, key=k["early"], format="%.2f%%")
    credit = s3.number_input("Credit allowance (CAD)", min_value=0.0, step=50.0, key=k["credit"],
                             format="%.2f")
    promo = s4.number_input("Promotional allowance (CAD)", min_value=0.0, step=50.0,
                            key=k["promo"], format="%.2f")

sim = simulate_frame(row_df, discount_rate=disc / 100, rebate_rate=rebate / 100,
                     early_rate=early / 100, credit_cad=credit, promo_cad=promo)
s = sim.iloc[0]
changed = abs(s["pocket_revenue_cad"] - row["pocket_revenue_cad"]) > 0.005
if disc > limit_pct + 1e-9:
    st.markdown(f":red[This discount ({disc:.1f}%) is above the contract's approved maximum "
                f"({limit_pct:.1f}%).]")
if not changed:
    st.info("Nothing has changed yet. Move the slider or click a quick option.")

d_rev = s["pocket_revenue_cad"] - row["pocket_revenue_cad"]
d_mar = s["pocket_margin_cad"] - row["pocket_margin_cad"]
m1, m2, m3 = st.columns(3)
m1.metric("Pocket revenue (what-if)", money(s["pocket_revenue_cad"]),
          f"{d_rev:+,.0f} CAD vs original {money(row['pocket_revenue_cad'])}",
          delta_color="off", delta_arrow="off")
m2.metric("Pocket margin (what-if)", money(s["pocket_margin_cad"]),
          f"{d_mar:+,.0f} CAD vs original {money(row['pocket_margin_cad'])}",
          delta_color="off", delta_arrow="off")
m3.metric("Price reduction (what-if)", pct(s["reduction_rate"]),
          f"original {pct(row[TARGET])} · expected {pct(row[PREDICTED])}",
          delta_color="off", delta_arrow="off")
st.caption("A what-if, not real profit: it assumes the customer buys the same quantity at the "
           "new price. Part of the gain is paid back, because rebates are a percentage of "
           "invoice revenue and rise when the discount falls.")

left, right = st.columns([3, 2])
with left:
    st.plotly_chart(comparison_chart(row.to_dict(), s.to_dict()), width="stretch")
with right:
    lines = [("List revenue", LIST), ("On-invoice discount", DISCOUNT),
             ("Invoice revenue", "invoice_revenue_cad")]
    lines += [(label, col) for col, label in OFF_INVOICE]
    lines += [("Pocket revenue", "pocket_revenue_cad")]
    lines += [(label, col) for col, label in COST_TO_SERVE]
    lines += [("COGS", COGS), ("Pocket margin", "pocket_margin_cad")]
    compare = pd.DataFrame({
        "Step": [label for label, _ in lines],
        "Original": [row[col] for _, col in lines],
        "What-if": [s[col] for _, col in lines],
    })
    compare["Change"] = compare["What-if"] - compare["Original"]
    st.dataframe(compare, hide_index=True, width="stretch", height=420,
                 column_config={c: st.column_config.NumberColumn(format="%.0f")
                                for c in ("Original", "What-if")}
                 | {"Change": st.column_config.NumberColumn(format="%+.0f")})

tab_orig, tab_sim = st.tabs(["Original Price Waterfall", "What-if Price Waterfall"])
with tab_orig:
    st.plotly_chart(waterfall_chart(waterfall(row_df), height=500), width="stretch",
                    key="waterfall_original")
with tab_sim:
    st.plotly_chart(waterfall_chart(waterfall(sim), height=500), width="stretch",
                    key="waterfall_simulated")

st.divider()

# ------------------------------------------------------------- 4. portfolio
st.header("4. What if we did this for all unusual transactions?", anchor="portfolio")
scope = st.radio("Apply to all unusual transactions in the current selection", list(SCOPES),
                 horizontal=True, format_func=SCOPE_LABELS.get)
gap_share = 0.5
if scope != "Contract limit exceeded":
    gap_share = st.slider("How much of the gap to close", 0, 100, 50, step=5, format="%d%%") / 100
    st.caption("The gap is the extra reduction the model cannot explain. The discount is cut "
               "by this share of it, never by more than the discount itself.")

detail, summary = portfolio_scenario(view, scope, gap_share)
p1, p2, p3 = st.columns(3)
p1.metric("Transactions changed", f"{summary['n_affected']:,}")
p2.metric("Extra pocket revenue (what-if)", f"{summary['pocket_revenue_change']:+,.0f} CAD",
          f"{summary['pocket_revenue_change'] / summary['company_pocket_revenue']:.2%} of selection",
          delta_color="off", delta_arrow="off")
p3.metric("Extra pocket margin (what-if)", f"{summary['pocket_margin_change']:+,.0f} CAD",
          f"{summary['pocket_margin_change'] / summary['company_pocket_margin']:.2%} of selection",
          delta_color="off", delta_arrow="off")
st.caption(f"Discounts are cut by {summary['discount_cut_cad']:,.0f} CAD in total; "
           f"{summary['accrual_offset_cad']:,.0f} CAD of that is paid back through higher rebates. "
           "This is a what-if: customers may buy less at the higher price, and some of these "
           "discounts may have been justified.")
if detail.empty:
    st.info("No transaction is changed by this rule in the current selection.")
else:
    with st.expander("Show the transactions"):
        out = detail.rename(columns={
            "transaction_id": "Transaction ID", "customer_name": "Customer", "product_id": "Product",
            "province": "Region", "statistical_anomaly": "Higher than expected",
            "contract_limit_exceeded": "Above contract limit", "discount_cut_cad": "Discount cut (CAD)",
            "pocket_revenue_before": "Pocket revenue before",
            "pocket_revenue_after": "Pocket revenue what-if",
            "pocket_margin_before": "Pocket margin before",
            "pocket_margin_after": "Pocket margin what-if",
            "pocket_revenue_change": "Revenue change", "pocket_margin_change": "Margin change"})
        for col in ("Higher than expected", "Above contract limit"):
            out[col] = out[col].map({True: "Yes", False: "No"})
        st.dataframe(out, hide_index=True, width="stretch", height=320,
                     column_config={c: st.column_config.NumberColumn(format="%.0f")
                                    for c in out.columns if out[c].dtype.kind == "f"})
        st.download_button("Download this table (CSV)", out.to_csv(index=False).encode(),
                           "what_if_all_unusual_transactions.csv", "text/csv")
