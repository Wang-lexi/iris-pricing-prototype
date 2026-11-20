"""Streamlit page: Root Cause Diagnosis and Scenario Simulation (Model 3).

Takes the transactions flagged by the Regression Diagnosis, shows which deduction drives each
one, and lets a consultant test "what if the discount were lower?" against the Price Waterfall.

    streamlit run app/dashboard.py
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from src.diagnosis import (
    COMPONENTS,
    COST_TO_SERVE,
    SCOPES,
    STATISTICAL,
    POLICY,
    baseline_assumptions,
    component_table,
    evidence,
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

st.set_page_config(page_title="Root Cause & Scenarios", layout="wide")
st.markdown(
    "<style>.block-container{max-width:100%;padding-left:2.5rem;padding-right:2.5rem;}</style>",
    unsafe_allow_html=True)

SHARED_DEFAULTS = {"model_product_level": "category", "model_test_share": 0.20,
                   "model_top_share": 0.05}


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
st.sidebar.header("Model settings")
st.sidebar.caption("Shared with the Regression Diagnosis page, so both pages flag the same "
                   "transactions.")
for key, default in SHARED_DEFAULTS.items():
    st.session_state.setdefault(key, default)
    st.session_state[key] = st.session_state[key]
product_level = st.sidebar.radio("Product enters the model as", ["category", "id"],
                                 format_func=str.capitalize, key="model_product_level")
test_share = st.sidebar.slider("Share of latest transactions held out for testing",
                               0.10, 0.40, step=0.05, format="%.2f", key="model_test_share")
top_share = st.sidebar.slider("Flag the top share of residuals", 0.01, 0.20, step=0.01,
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
st.title("Root Cause Diagnosis and Scenario Simulation")
st.markdown(
    "Three different kinds of statement appear on this page. They are never mixed:\n\n"
    f"- :orange[**{STATISTICAL}**] — the regression says the reduction is bigger than quantity, "
    "tier, product, channel, region and month explain. Model-based; a reason to look, not a "
    "mistake.\n"
    f"- :red[**{POLICY}**] — the on-invoice discount is above the contract's approved maximum. "
    "A rule checked against contract data; whether it was approved is not in the data.\n"
    ":blue[**Hypothetical improvement**] — what pocket revenue and margin would be under "
    "assumptions you choose. A simulation, **not** recoverable profit: it assumes the customer "
    "buys the same quantity at the new price.")
st.caption("All data is synthetic.")
st.markdown(
    "**Jump to:** [1. Choose](#choose) · [2. Evidence](#evidence) · [3. Root cause](#cause) · "
    "[4. Simulate](#simulate) · [5. Portfolio](#portfolio)")
if view.empty:
    st.warning("No transactions match the current filters.")
    st.stop()

# ----------------------------------------------------------------- 1. choose
st.header("1. Choose a flagged transaction", anchor="choose")
show = st.radio("Show", ["Either flag", f"{STATISTICAL}", f"{POLICY}"], horizontal=True)
mask = {"Either flag": view["any_exception"], STATISTICAL: view["statistical_exception"],
        POLICY: view["policy_exception"]}[show]
candidates = view[mask].sort_values(RESIDUAL, ascending=False)
st.caption(f"{len(candidates):,} transactions, largest residual first. "
           f"Statistical flag: residual of {threshold * 100:+.1f} pp or more "
           f"(top {top_share:.0%}).")
if candidates.empty:
    st.info("No flagged transactions in the current selection.")
    st.stop()

yes_no = {True: "Yes", False: "No"}
st.dataframe(pd.DataFrame({
    "Transaction ID": candidates["transaction_id"],
    "Customer": candidates["customer_name"],
    "Product": candidates["product_id"] + " · " + candidates["product_category"],
    "Region": candidates["province"],
    "Actual reduction %": candidates[TARGET] * 100,
    "Expected reduction %": candidates[PREDICTED] * 100,
    "Residual (pp)": candidates[RESIDUAL] * 100,
    STATISTICAL: candidates["statistical_exception"].map(yes_no),
    POLICY: candidates["policy_exception"].map(yes_no),
    "Price override": candidates["price_override_used"],
}), hide_index=True, width="stretch", height=280,
    column_config={"Actual reduction %": st.column_config.NumberColumn(format="%.1f"),
                   "Expected reduction %": st.column_config.NumberColumn(format="%.1f"),
                   "Residual (pp)": st.column_config.NumberColumn(format="%+.1f")})

by_id = candidates.set_index("transaction_id")
tx_id = st.selectbox(
    "Transaction", list(by_id.index), index=None, placeholder="Choose a transaction",
    format_func=lambda t: (f"{t} · {by_id.loc[t, 'customer_name']} · "
                           f"residual {by_id.loc[t, RESIDUAL] * 100:+.1f} pp"
                           f"{' · over contract limit' if by_id.loc[t, 'policy_exception'] else ''}"))
if tx_id is None:
    st.info("Choose a transaction above to diagnose it.")
    st.stop()

row_df = flagged[flagged["transaction_id"] == tx_id]
row = row_df.iloc[0]
st.markdown(
    f"**{row['customer_name']}** — **Product:** {row['product_id']} · {row['product_category']} · "
    f"**Tier:** {row['customer_tier']} · **Channel:** {row['sales_channel']} · "
    f"**Province:** {row['province']} · **Date:** {row['transaction_date'].date()} · "
    f"**Quantity:** {row['quantity_units']:,.0f}")

st.divider()

# --------------------------------------------------------------- 2. evidence
st.header("2. Evidence", anchor="evidence")
st.caption("Three separate pieces of evidence about this transaction.")
ev = evidence(row, threshold)
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(f"**{STATISTICAL}**")
    st.markdown(":orange[**Flagged**]" if ev[STATISTICAL]["flag"] else "Not flagged")
    st.caption(ev[STATISTICAL]["text"])
with c2:
    st.markdown(f"**{POLICY}**")
    st.markdown(":red[**Exceeded**]" if ev[POLICY]["flag"] else ":green[Within limit]")
    st.caption(ev[POLICY]["text"])
with c3:
    st.markdown("**Price override**")
    st.markdown("**Used**" if ev["Price override"]["flag"] else "Not used")
    st.caption(ev["Price override"]["text"])

st.divider()

# ----------------------------------------------------------------- 3. cause
st.header("3. Root cause: which deduction?", anchor="cause")
st.caption(f"Each deduction between list revenue and pocket revenue, compared with the median of "
           f"all {row['customer_tier']}-tier transactions, as a share of list revenue.")
table = component_table(row, peers)
left, right = st.columns([3, 2])
with left:
    st.plotly_chart(component_excess_chart(table), width="stretch")
with right:
    st.markdown("\n".join(f"- {n}" for n in narrative(row, table)))
view_table = table[["component", "amount_cad", "pct_of_list", "peer_median_pct", "excess_pp",
                    "share_of_deductions"]].copy()
view_table["share_of_deductions"] *= 100
view_table.columns = ["Deduction", "Amount (CAD)", "% of list", "Tier-peer median %",
                      "Above peers (pp)", "Share of deductions %"]
st.dataframe(view_table, hide_index=True, width="stretch",
             column_config={"Amount (CAD)": st.column_config.NumberColumn(format="%.0f"),
                            "% of list": st.column_config.NumberColumn(format="%.2f"),
                            "Tier-peer median %": st.column_config.NumberColumn(format="%.2f"),
                            "Above peers (pp)": st.column_config.NumberColumn(format="%+.2f"),
                            "Share of deductions %": st.column_config.NumberColumn(format="%.0f")})
st.caption("The five deductions add up to list revenue minus pocket revenue, so nothing is "
           "counted twice. A deduction above its peers can still be legitimate (for example a "
           "negotiated bid); the comparison says where to ask questions.")

st.divider()

# -------------------------------------------------------------- 4. simulate
st.header("4. Scenario simulation", anchor="simulate")
st.markdown(":blue[**Hypothetical.**] Change the assumptions and compare with the original. "
            "Quantity, list price, COGS and cost-to-serve stay as they are, and the customer "
            "is assumed to buy the same quantity at the new price.")

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

st.markdown("**Quick scenarios** (they only ever lower the discount):")
b1, b2, b3, b4 = st.columns(4)
b1.button("Reset to original", on_click=apply, args=(orig,), width="stretch")
b2.button(f"Cap at contract limit ({limit_pct:.1f}%)", width="stretch", on_click=apply,
          args=({"disc": min(orig["disc"], limit_pct)},))
b3.button(f"Tier-peer median ({peer_pct:.1f}%)", width="stretch", on_click=apply,
          args=({"disc": min(orig["disc"], peer_pct)},),
          help="The median on-invoice discount of this customer's tier.")
b4.button(f"Model-expected reduction ({expected_pct:.1f}%)", width="stretch", on_click=apply,
          args=({"disc": expected_pct},),
          help="The discount at which the total price reduction equals what the regression "
               "expects for this transaction.")

s1, s2, s3 = st.columns(3)
disc = s1.slider("On-invoice discount (% of list revenue)", 0.0, max(40.0, orig["disc"] + 5), step=0.1,
                 key=k["disc"], format="%.1f%%")
rebate = s2.slider("Volume rebate rate (% of invoice revenue)", 0.0, max(10.0, orig["rebate"] * 1.5),
                   step=0.05, key=k["rebate"], format="%.2f%%")
early = s3.slider("Early-payment discount (% of invoice revenue)", 0.0,
                  max(5.0, orig["early"] * 1.5), step=0.05, key=k["early"], format="%.2f%%")
n1, n2 = st.columns(2)
credit = n1.number_input("Credit allowance (CAD)", min_value=0.0, step=50.0, key=k["credit"],
                         format="%.2f")
promo = n2.number_input("Promotional allowance (CAD)", min_value=0.0, step=50.0, key=k["promo"],
                        format="%.2f")

sim = simulate_frame(row_df, discount_rate=disc / 100, rebate_rate=rebate / 100,
                     early_rate=early / 100, credit_cad=credit, promo_cad=promo)
s = sim.iloc[0]
changed = abs(s["pocket_revenue_cad"] - row["pocket_revenue_cad"]) > 0.005
if disc > limit_pct + 1e-9:
    st.markdown(f":red[The simulated discount ({disc:.1f}%) is above the contract's approved "
                f"maximum ({limit_pct:.1f}%).]")
st.caption("Rebate and early-payment accruals are contract rates on invoice revenue, so they "
           "rise a little when the discount falls. Credit and promotional allowances are lump "
           "sums in CAD.")

if not changed:
    st.info("No assumption has been changed yet. Move a slider or use a quick scenario.")

d_rev = s["pocket_revenue_cad"] - row["pocket_revenue_cad"]
d_mar = s["pocket_margin_cad"] - row["pocket_margin_cad"]
mar_pct0 = row["pocket_margin_cad"] / row["pocket_revenue_cad"]
mar_pct1 = s["pocket_margin_cad"] / s["pocket_revenue_cad"]
m1, m2, m3, m4 = st.columns(4)
m1.metric("Pocket revenue: simulated", money(s["pocket_revenue_cad"]),
          f"{d_rev:+,.0f} CAD vs original {money(row['pocket_revenue_cad'])}",
          delta_color="off", delta_arrow="off")
m2.metric("Pocket margin: simulated", money(s["pocket_margin_cad"]),
          f"{d_mar:+,.0f} CAD vs original {money(row['pocket_margin_cad'])}",
          delta_color="off", delta_arrow="off")
m3.metric("Margin % of pocket revenue", pct(mar_pct1), f"original {pct(mar_pct0)}",
          delta_color="off", delta_arrow="off")
m4.metric("Total price reduction", pct(s["reduction_rate"]),
          f"original {pct(row[TARGET])} · expected {pct(row[PREDICTED])}",
          delta_color="off", delta_arrow="off")

lines = [("List revenue", LIST), ("On-invoice discount", DISCOUNT),
         ("Invoice revenue", "invoice_revenue_cad")]
lines += [(label, col) for col, label in OFF_INVOICE]
lines += [("Pocket revenue", "pocket_revenue_cad")]
lines += [(label, col) for col, label in COST_TO_SERVE] + [("COGS", COGS),
                                                           ("Pocket margin", "pocket_margin_cad")]
compare = pd.DataFrame({
    "Step": [label for label, _ in lines],
    "Original (CAD)": [row[col] for _, col in lines],
    "Simulated (CAD, hypothetical)": [s[col] for _, col in lines],
})
compare["Change (CAD)"] = compare["Simulated (CAD, hypothetical)"] - compare["Original (CAD)"]
left, right = st.columns([2, 3])
with left:
    st.dataframe(compare, hide_index=True, width="stretch", height=460,
                 column_config={c: st.column_config.NumberColumn(format="%.0f")
                                for c in compare.columns[1:3]}
                 | {"Change (CAD)": st.column_config.NumberColumn(format="%+.0f")})
with right:
    st.plotly_chart(comparison_chart(row.to_dict(), s.to_dict()), width="stretch")

tab_orig, tab_sim = st.tabs(["Original Price Waterfall", "Simulated Price Waterfall (hypothetical)"])
with tab_orig:
    st.plotly_chart(waterfall_chart(waterfall(row_df), height=500), width="stretch",
                    key="waterfall_original")
with tab_sim:
    st.plotly_chart(waterfall_chart(waterfall(sim), height=500), width="stretch",
                    key="waterfall_simulated")

st.divider()

# ------------------------------------------------------------- 5. portfolio
st.header("5. Portfolio view of the same idea", anchor="portfolio")
st.markdown(":blue[**Hypothetical.**] Apply one rule to every flagged transaction in the "
            "current selection and add up the effect on pocket revenue and pocket margin.")
scope = st.radio("Apply to", list(SCOPES), horizontal=True,
                 format_func=lambda s_: {"Either": "Either flag"}.get(s_, s_))
st.caption(SCOPES[scope] + ".")
gap_share = 0.5
if scope != "Contract limit exceeded":
    gap_share = st.slider("Share of the unexplained reduction to close", 0, 100, 50, step=5,
                          format="%d%%") / 100
    st.caption("Unexplained reduction = residual x list revenue. The discount is cut by this "
               "share of it, never by more than the discount itself.")

detail, summary = portfolio_scenario(view, scope, gap_share)
p1, p2, p3, p4 = st.columns(4)
p1.metric("Transactions changed", f"{summary['n_affected']:,}")
p2.metric("Hypothetical pocket revenue", f"{summary['pocket_revenue_change']:+,.0f} CAD",
          f"{summary['pocket_revenue_change'] / summary['company_pocket_revenue']:.2%} of selection",
          delta_color="off", delta_arrow="off")
p3.metric("Hypothetical pocket margin", f"{summary['pocket_margin_change']:+,.0f} CAD",
          f"{summary['pocket_margin_change'] / summary['company_pocket_margin']:.2%} of selection",
          delta_color="off", delta_arrow="off")
p4.metric("Discount cut", f"{summary['discount_cut_cad']:,.0f} CAD",
          f"{summary['accrual_offset_cad']:,.0f} CAD offset by rebate accruals",
          delta_color="off", delta_arrow="off")
st.warning("These are hypothetical changes under the rule above, not recoverable profit. They "
           "assume customers keep buying the same quantity at the new price, which flagged "
           "transactions often will not; some of these discounts may have been justified.")
if detail.empty:
    st.info("No transaction is changed by this rule in the current selection.")
else:
    shown = detail.rename(columns={
        "transaction_id": "Transaction ID", "customer_name": "Customer", "product_id": "Product",
        "province": "Region", "statistical_anomaly": STATISTICAL,
        "contract_limit_exceeded": POLICY, "discount_cut_cad": "Discount cut (CAD)",
        "pocket_revenue_before": "Pocket revenue before", "pocket_revenue_after": "after (hypothetical)",
        "pocket_margin_before": "Pocket margin before", "pocket_margin_after": "margin after (hypothetical)",
        "pocket_revenue_change": "Revenue change", "pocket_margin_change": "Margin change"})
    for col in (STATISTICAL, POLICY):
        shown[col] = shown[col].map(yes_no)
    st.dataframe(shown, hide_index=True, width="stretch", height=320,
                 column_config={c: st.column_config.NumberColumn(format="%.0f")
                                for c in shown.columns if shown[c].dtype.kind == "f"})
    st.download_button("Download this table (CSV)", shown.to_csv(index=False).encode(),
                       "portfolio_scenario.csv", "text/csv")
