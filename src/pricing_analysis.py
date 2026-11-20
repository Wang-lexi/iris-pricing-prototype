"""Model 1: Pocket Price Waterfall.

Math (per transaction line i, all amounts in CAD):

    L  = list revenue                = quantity * list unit price
    D  = on-invoice discount
    I  = invoice revenue             = L - D
    R  = volume rebate accrual           \\
    E  = early payment discount           |  off-invoice deductions
    C  = credit allowance                 |
    P  = promotional allowance           /
    PR = pocket revenue              = I - R - E - C - P
    S  = cost to serve               = freight + handling
    G  = COGS
    PM = pocket margin               = PR - S - G

Aggregation rule: rates for any group are ratios of SUMS, never an average of
per-transaction ratios. Large orders must weigh more than small ones, and the
group's waterfall must add up to the total waterfall.

    leakage rate of step k  = sum(step_k) / sum(L)
    pocket price realization = sum(PR) / sum(L)  = 1 - total leakage rate
    pocket margin %          = sum(PM) / sum(PR)
"""

import pandas as pd

# (column in the transaction table, label shown in the waterfall)
DEDUCTIONS = [
    ("on_invoice_discount_cad", "On-invoice discount"),
    ("volume_rebate_accrual_cad", "Volume rebate"),
    ("early_payment_discount_cad", "Early payment discount"),
    ("credit_allowance_cad", "Credit allowance"),
    ("promotional_allowance_cad", "Promotional allowance"),
]
COST_TO_SERVE = [
    ("freight_cost_to_serve_cad", "Freight"),
    ("handling_cost_to_serve_cad", "Handling"),
]
LIST_COL = "list_revenue_cad"
COGS_COL = "cogs_total_cad"

DEDUCTION_COLS = [c for c, _ in DEDUCTIONS]
CTS_COLS = [c for c, _ in COST_TO_SERVE]
LABELS = dict(DEDUCTIONS + COST_TO_SERVE)

TOLERANCE = 0.01  # CAD; floating point / rounding slack for the identity checks


def add_waterfall_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add invoice / pocket revenue, cost to serve and pocket margin columns."""
    out = df.copy()
    out["invoice_revenue_calc_cad"] = out[LIST_COL] - out["on_invoice_discount_cad"]
    out["off_invoice_total_cad"] = out[DEDUCTION_COLS[1:]].sum(axis=1)
    out["pocket_revenue_cad"] = out["invoice_revenue_calc_cad"] - out["off_invoice_total_cad"]
    out["cost_to_serve_cad"] = out[CTS_COLS].sum(axis=1)
    out["pocket_margin_cad"] = out["pocket_revenue_cad"] - out["cost_to_serve_cad"] - out[COGS_COL]
    out["pocket_price_per_unit_cad"] = out["pocket_revenue_cad"] / out["quantity_units"]
    return out


def check_waterfall(df: pd.DataFrame) -> dict[str, float]:
    """Reconcile the computed waterfall against the source data.

    Returns the largest absolute gap (CAD) for each check; all should be ~0.
    """
    return {
        "invoice_revenue_vs_source": (
            df["invoice_revenue_calc_cad"] - df["invoice_revenue_cad"]
        ).abs().max(),
        "list_minus_all_steps_vs_margin": (
            df[LIST_COL]
            - df[DEDUCTION_COLS].sum(axis=1)
            - df["cost_to_serve_cad"]
            - df[COGS_COL]
            - df["pocket_margin_cad"]
        ).abs().max(),
    }


def waterfall_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Long-form waterfall for the whole (filtered) table.

    Columns: step, label, amount_cad (signed), pct_of_list, kind.
    kind is 'total' for subtotals and 'delta' for deductions.
    """
    s = df.sum(numeric_only=True)
    list_rev = s[LIST_COL]

    rows = [("list", "List revenue", s[LIST_COL], "total")]
    for col, label in DEDUCTIONS[:1]:
        rows.append((col, label, -s[col], "delta"))
    rows.append(("invoice", "Invoice revenue", s["invoice_revenue_calc_cad"], "total"))
    for col, label in DEDUCTIONS[1:]:
        rows.append((col, label, -s[col], "delta"))
    rows.append(("pocket", "Pocket revenue", s["pocket_revenue_cad"], "total"))
    for col, label in COST_TO_SERVE:
        rows.append((col, label, -s[col], "delta"))
    rows.append((COGS_COL, "COGS", -s[COGS_COL], "delta"))
    rows.append(("margin", "Pocket margin", s["pocket_margin_cad"], "total"))

    out = pd.DataFrame(rows, columns=["step", "label", "amount_cad", "kind"])
    out["pct_of_list"] = out["amount_cad"] / list_rev
    return out


def segment_summary(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """One row per segment with revenue totals and ratio-of-sums leakage rates."""
    sum_cols = [LIST_COL, "invoice_revenue_calc_cad", "pocket_revenue_cad",
                "cost_to_serve_cad", COGS_COL, "pocket_margin_cad",
                "quantity_units", *DEDUCTION_COLS]
    g = df.groupby(by, observed=True)[sum_cols].sum()
    g["n_transactions"] = df.groupby(by, observed=True).size()

    for col, label in DEDUCTIONS:
        g[f"{col}_rate"] = g[col] / g[LIST_COL]
    g["invoice_leakage_rate"] = g["on_invoice_discount_cad_rate"]
    g["off_invoice_leakage_rate"] = (
        g[DEDUCTION_COLS[1:]].sum(axis=1) / g[LIST_COL]
    )
    g["total_leakage_rate"] = 1 - g["pocket_revenue_cad"] / g[LIST_COL]
    g["pocket_price_realization"] = g["pocket_revenue_cad"] / g[LIST_COL]
    g["pocket_margin_pct"] = g["pocket_margin_cad"] / g["pocket_revenue_cad"]
    g["leakage_cad"] = g[LIST_COL] - g["pocket_revenue_cad"]
    return g.reset_index().sort_values("total_leakage_rate", ascending=False)


def whale_curve(df: pd.DataFrame, customer_col: str = "customer_id") -> pd.DataFrame:
    """Cumulative pocket margin by customer, best to worst.

    cum_margin_pct is cumulative pocket margin as a % of the total. It rises
    above 100% when the tail of customers destroys value, then falls to 100%.
    """
    c = (df.groupby(customer_col)["pocket_margin_cad"].sum()
           .sort_values(ascending=False).reset_index())
    c["cum_margin_cad"] = c["pocket_margin_cad"].cumsum()
    total = c["pocket_margin_cad"].sum()
    c["cum_margin_pct"] = c["cum_margin_cad"] / total
    c["cum_customers_pct"] = (c.index + 1) / len(c)
    return c
