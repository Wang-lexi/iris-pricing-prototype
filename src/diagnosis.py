"""Root cause diagnosis and scenario simulation (Model 3).

Builds on the Price Waterfall (`pricing_analysis`) and the Regression Diagnosis (`regression`).

Three kinds of statement are kept strictly apart:

1. STATISTICAL ANOMALY   the regression residual is in the top share of residuals
                         (model based; "unexplained by the model", not a mistake).
2. CONTRACT LIMIT        the on-invoice discount is above the contract's approved maximum
   EXCEEDED              (a rule checked against contract data; whether the exception was
                         approved is not in the data).
3. HYPOTHETICAL          what pocket revenue and margin would be under assumptions chosen by
   IMPROVEMENT           the user. A simulation output, never recoverable profit.

Simulation rules (all transactions): quantity, list price, COGS and cost-to-serve stay as they
are, and the customer is assumed to buy the same quantity at the new price (no price response).
The on-invoice discount is a share of list revenue. Volume rebate and early-payment discount
are contract rates on *invoice revenue* (confirmed in the data), so they are recomputed when
the discount changes. Credit and promotional allowances are lump sums and stay in CAD unless
changed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .pricing_analysis import COGS, COST_TO_SERVE, DISCOUNT, LIST, OFF_INVOICE
from .regression import PREDICTED, RESIDUAL, TARGET

VOLUME_REBATE, EARLY_PAYMENT, CREDIT, PROMO = (c for c, _ in OFF_INVOICE)

# the five deduction components between list revenue and pocket revenue
COMPONENTS = [(DISCOUNT, "On-invoice discount")] + list(OFF_INVOICE)

# A component must exceed its tier-peer median by at least this much (percentage points of list
# revenue) before it is named as a main driver. About half the regression's typical error
# (RMSE 2.7 pp): with it, 9% of ordinary transactions and 82% of statistical anomalies get a
# named driver. A lower bar would name a "driver" for most ordinary transactions.
MIN_DRIVER_EXCESS_PP = 1.5

STATISTICAL = "Statistical anomaly"
POLICY = "Contract limit exceeded"
HYPOTHETICAL = "Hypothetical improvement"


# ------------------------------------------------------------ root cause
def peer_rates(data: pd.DataFrame) -> pd.DataFrame:
    """Median deduction rate (share of list revenue) of each customer tier, per component.

    Customer tier is the strongest legitimate driver in the regression, so tier peers are
    the fairest comparison for a single transaction.
    """
    rates = data[[c for c, _ in COMPONENTS]].div(data[LIST], axis=0)
    return rates.groupby(data["customer_tier"]).median()


def component_table(row: pd.Series, peers: pd.DataFrame) -> pd.DataFrame:
    """Each deduction of one transaction, against the median of its tier peers.

    Columns: component, amount_cad, pct_of_list, peer_median_pct, excess_pp, share_of_deductions.
    The five amounts add up to list revenue minus pocket revenue, so nothing is counted twice.
    """
    rows = []
    total = sum(row[c] for c, _ in COMPONENTS)
    for col, label in COMPONENTS:
        rate = row[col] / row[LIST]
        peer = peers.loc[row["customer_tier"], col]
        rows.append({
            "component": label, "column": col, "amount_cad": row[col],
            "pct_of_list": rate * 100, "peer_median_pct": peer * 100,
            "excess_pp": (rate - peer) * 100,
            "share_of_deductions": row[col] / total if total else 0.0,
        })
    return pd.DataFrame(rows)


def main_driver(table: pd.DataFrame) -> pd.Series | None:
    """The component furthest above its peers, or None if none is clearly above."""
    top = table.loc[table["excess_pp"].idxmax()]
    return top if top["excess_pp"] >= MIN_DRIVER_EXCESS_PP else None


def evidence(row: pd.Series, threshold: float) -> dict[str, dict]:
    """The three separate kinds of evidence for one transaction, each with its own wording."""
    residual_pp = row[RESIDUAL] * 100
    statistical = {
        "flag": bool(row["statistical_exception"]),
        "text": (f"Actual reduction {row[TARGET]:.1%} vs {row[PREDICTED]:.1%} expected "
                 f"({residual_pp:+.1f} pp). Flag threshold {threshold * 100:+.1f} pp. "
                 "Model-based: a bigger reduction than the model explains, not proof of a mistake."),
    }
    limit = row["approved_max_on_invoice_discount_rate"]
    policy = {
        "flag": bool(row["policy_exception"]),
        "text": (f"On-invoice discount {row['discount_rate']:.1%} of list vs approved maximum "
                 f"{limit:.1%}"
                 + (f": {row['excess_discount_pp']:.1f} pp above the limit." if row["policy_exception"]
                    else ": within the limit.")
                 + " Rule-based; whether it was approved is not in the data."),
    }
    override = {
        "flag": row["price_override_used"] == "Y",
        "text": f"Manual price override used: {row['price_override_used']}. Context for the "
                "investigation only; it is not used by the model.",
    }
    return {STATISTICAL: statistical, POLICY: policy, "Price override": override}


def narrative(row: pd.Series, table: pd.DataFrame) -> list[str]:
    """The root cause in plain language: how big the gap is, what drives it, contract and override."""
    tier = row["customer_tier"]
    gap = row[RESIDUAL] * 100
    notes = [f"This transaction gave away **{row[TARGET]:.1%}** of the list price. Similar {tier} "
             f"customers get about **{row[PREDICTED]:.1%}**"
             + (f" ({gap:.1f} percentage points less)." if gap < 0 else f" ({gap:.1f} points more).")]
    driver = main_driver(table)
    if driver is None:
        notes.append("No single deduction stands out; the difference is small or spread across "
                     "several.")
    else:
        notes.append(f"The cause is the **{driver['component'].lower()}**: "
                     f"**{driver['pct_of_list']:.1f}%** of list price, against about "
                     f"{driver['peer_median_pct']:.1f}% typical for {tier} customers "
                     f"({driver['amount_cad']:,.0f} CAD).")
    for _, o in table[(table["excess_pp"] >= MIN_DRIVER_EXCESS_PP)
                      & (table["component"] != (driver["component"] if driver is not None else ""))].iterrows():
        notes.append(f"{o['component']} is also above typical ({o['excess_pp']:+.1f} points).")
    limit = row["approved_max_on_invoice_discount_rate"]
    if row["policy_exception"]:
        notes.append(f":red[**Above the contract limit:**] the contract allows at most {limit:.1%}; "
                     f"this discount is {row['discount_rate']:.1%}.")
    else:
        notes.append(f"Within the contract limit (the contract allows up to {limit:.1%}; "
                     f"this discount is {row['discount_rate']:.1%}).")
    if row["price_override_used"] == "Y":
        notes.append("A manual price override was used on this transaction.")
    return notes


# ------------------------------------------------------------ simulation
def baseline_assumptions(df: pd.DataFrame) -> dict[str, pd.Series]:
    """The assumptions that reproduce the current data exactly (rates as shares, lump sums in CAD)."""
    invoice = df[LIST] - df[DISCOUNT]
    safe_invoice = invoice.where(invoice != 0)
    return {
        "discount_rate": df[DISCOUNT] / df[LIST],
        "rebate_rate": (df[VOLUME_REBATE] / safe_invoice).fillna(0.0),
        "early_rate": (df[EARLY_PAYMENT] / safe_invoice).fillna(0.0),
        "credit_cad": df[CREDIT].astype(float),
        "promo_cad": df[PROMO].astype(float),
    }


def simulate_frame(df: pd.DataFrame, discount_rate=None, rebate_rate=None, early_rate=None,
                   credit_cad=None, promo_cad=None) -> pd.DataFrame:
    """Recalculate the waterfall under new assumptions. Omitted assumptions stay as they are.

    Each argument can be a single number or one value per row. The result has the same column
    names as the source table, so it can go straight into `pricing_analysis.waterfall`.
    """
    base = baseline_assumptions(df)
    given = {"discount_rate": discount_rate, "rebate_rate": rebate_rate, "early_rate": early_rate,
             "credit_cad": credit_cad, "promo_cad": promo_cad}
    a = {k: base[k] if v is None else pd.Series(v, index=df.index, dtype=float)
         for k, v in given.items()}

    out = pd.DataFrame(index=df.index)
    out[LIST] = df[LIST]
    out[DISCOUNT] = a["discount_rate"] * df[LIST]
    out["invoice_revenue_cad"] = out[LIST] - out[DISCOUNT]
    out[VOLUME_REBATE] = a["rebate_rate"] * out["invoice_revenue_cad"]
    out[EARLY_PAYMENT] = a["early_rate"] * out["invoice_revenue_cad"]
    out[CREDIT] = a["credit_cad"]
    out[PROMO] = a["promo_cad"]
    off = [c for c, _ in OFF_INVOICE]
    out["pocket_revenue_cad"] = out["invoice_revenue_cad"] - out[off].sum(axis=1)
    for col, _ in COST_TO_SERVE:
        out[col] = df[col]
    out[COGS] = df[COGS]
    out["pocket_margin_cad"] = (out["pocket_revenue_cad"] - out[[c for c, _ in COST_TO_SERVE]].sum(axis=1)
                                - out[COGS])
    out["reduction_rate"] = (out[LIST] - out["pocket_revenue_cad"]) / out[LIST]
    return out


def expected_discount_rate(row: pd.Series) -> float:
    """On-invoice discount rate at which the total reduction equals the model's expectation.

    Solves  reduction = d + (1 - d) * (rebate_rate + early_rate) + (credit + promo) / list
    for d, keeping the other assumptions as they are. Never above the current discount.
    """
    invoice = float(row[LIST] - row[DISCOUNT])
    r = float((row[VOLUME_REBATE] + row[EARLY_PAYMENT]) / invoice) if invoice else 0.0
    lump = (row[CREDIT] + row[PROMO]) / row[LIST]
    d = (row[PREDICTED] - r - lump) / (1 - r)
    return float(min(max(d, 0.0), row["discount_rate"]))


# ------------------------------------------------------------- portfolio
SCOPES = {
    "Contract limit exceeded": "Cap the on-invoice discount at the contract's approved maximum",
    "Statistical anomaly": "Close part of the gap between actual and expected reduction",
    "Either": "Larger of the two reductions for each transaction (never added together)",
}


def portfolio_scenario(flagged: pd.DataFrame, scope: str, gap_share: float
                       ) -> tuple[pd.DataFrame, dict]:
    """Hypothetical effect of reducing the on-invoice discount on flagged transactions.

    - Contract limit exceeded: discount capped at limit x list revenue.
    - Statistical anomaly: the discount is cut by `gap_share` of the unexplained reduction
      (residual x list revenue), never by more than the discount itself.
    - Either: for a transaction in both groups the larger cut is used, not the sum.

    Rebates and early-payment discounts are recomputed on the new invoice revenue, so part of
    every discount cut is offset by higher accruals. Returns (affected rows, summary).
    """
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {list(SCOPES)}")
    if not 0 <= gap_share <= 1:
        raise ValueError("gap_share must be between 0 and 1")

    discount, list_rev = flagged[DISCOUNT], flagged[LIST]
    limit_cut = np.where(
        flagged["policy_exception"],
        (discount - flagged["approved_max_on_invoice_discount_rate"] * list_rev).clip(lower=0), 0.0)
    gap_cut = np.where(
        flagged["statistical_exception"] & (flagged[RESIDUAL] > 0),
        np.minimum(discount, gap_share * flagged[RESIDUAL] * list_rev), 0.0)
    cut = {"Contract limit exceeded": limit_cut, "Statistical anomaly": gap_cut,
           "Either": np.maximum(limit_cut, gap_cut)}[scope]
    cut = pd.Series(cut, index=flagged.index)

    sim = simulate_frame(flagged, discount_rate=(discount - cut) / list_rev)
    affected = cut > 0
    detail = pd.DataFrame({
        "transaction_id": flagged["transaction_id"], "customer_name": flagged["customer_name"],
        "product_id": flagged["product_id"], "province": flagged["province"],
        "statistical_anomaly": flagged["statistical_exception"],
        "contract_limit_exceeded": flagged["policy_exception"],
        "discount_cut_cad": cut,
        "pocket_revenue_before": flagged["pocket_revenue_cad"],
        "pocket_revenue_after": sim["pocket_revenue_cad"],
        "pocket_margin_before": flagged["pocket_margin_cad"],
        "pocket_margin_after": sim["pocket_margin_cad"],
    })[affected]
    detail["pocket_revenue_change"] = detail["pocket_revenue_after"] - detail["pocket_revenue_before"]
    detail["pocket_margin_change"] = detail["pocket_margin_after"] - detail["pocket_margin_before"]
    detail = detail.sort_values("pocket_margin_change", ascending=False)

    summary = {
        "n_affected": int(affected.sum()),
        "discount_cut_cad": float(cut.sum()),
        "pocket_revenue_change": float(detail["pocket_revenue_change"].sum()),
        "pocket_margin_change": float(detail["pocket_margin_change"].sum()),
        "accrual_offset_cad": float(cut.sum() - detail["pocket_revenue_change"].sum()),
        "company_pocket_revenue": float(flagged["pocket_revenue_cad"].sum()),
        "company_pocket_margin": float(flagged["pocket_margin_cad"].sum()),
    }
    return detail, summary
