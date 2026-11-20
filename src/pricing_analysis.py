"""Pocket price waterfall (pure calculation, no statistical model).

Per transaction line (CAD):
    list revenue      L  = quantity x list unit price
    invoice revenue   I  = L - on-invoice discount
    pocket revenue    PR = I - volume rebate - early payment discount
                             - credit allowance - promotional allowance
    pocket margin     PM = PR - cost to serve (freight + handling) - COGS

Price leakage = L - PR (discounts and allowances only). Cost to serve and COGS
are shown to reach margin but are not counted as leakage.

Every percentage is sum(step) / sum(list revenue): a ratio of sums, not an
average of per-transaction ratios, so large orders weigh more.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "model1_waterfall_input.csv"

LIST = "list_revenue_cad"
DISCOUNT = "on_invoice_discount_cad"
OFF_INVOICE = [
    ("volume_rebate_accrual_cad", "Volume rebate"),
    ("early_payment_discount_cad", "Early payment discount"),
    ("credit_allowance_cad", "Credit allowance"),
    ("promotional_allowance_cad", "Promotional allowance"),
]
COST_TO_SERVE = [
    ("freight_cost_to_serve_cad", "Freight"),
    ("handling_cost_to_serve_cad", "Handling"),
]
COGS = "cogs_total_cad"


REQUIRED_COLS = [LIST, DISCOUNT, COGS]
OPTIONAL_ZERO_COLS = [c for c, _ in OFF_INVOICE + COST_TO_SERVE]


def prepare_input(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Validate a table and make it ready for `waterfall`.

    Required: list revenue, on-invoice discount, COGS (must be numeric, no blanks).
    Allowances, rebates and cost-to-serve columns are optional by nature: a missing
    column or a blank cell is treated as 0. Returns (clean table, notes for the user).
    """
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")

    out = df.copy()
    notes: list[str] = []
    for c in REQUIRED_COLS:
        out[c] = pd.to_numeric(out[c], errors="coerce")
        if out[c].isna().any():
            raise ValueError(f"Column '{c}' has {int(out[c].isna().sum())} blank or "
                             "non-numeric values; it must be fully numeric.")
    for c in OPTIONAL_ZERO_COLS:
        if c not in out.columns:
            out[c] = 0.0
            notes.append(f"Column '{c}' not found; treated as 0.")
        else:
            out[c] = pd.to_numeric(out[c], errors="coerce")
            n_blank = int(out[c].isna().sum())
            if n_blank:
                out[c] = out[c].fillna(0.0)
                notes.append(f"Column '{c}': {n_blank} blank/non-numeric value(s) treated as 0.")

    if "transaction_date" in out.columns:
        out["transaction_date"] = pd.to_datetime(out["transaction_date"], errors="coerce")
        if out["transaction_date"].notna().any():
            out["month"] = out["transaction_date"].dt.to_period("M").dt.to_timestamp()
    return out, notes


def load_input(path: Path = DATA_PATH) -> pd.DataFrame:
    """The bundled sample (synthetic) data."""
    return prepare_input(pd.read_csv(path))[0]


def waterfall(df: pd.DataFrame) -> pd.DataFrame:
    """Waterfall for the rows given (all rows, or a filtered subset).

    Columns: step, label, amount_cad (signed), pct_of_list, kind ('total' or 'delta').
    """
    s = df[[LIST, DISCOUNT, COGS] + [c for c, _ in OFF_INVOICE + COST_TO_SERVE]].sum()

    invoice = s[LIST] - s[DISCOUNT]
    pocket = invoice - sum(s[c] for c, _ in OFF_INVOICE)
    margin = pocket - sum(s[c] for c, _ in COST_TO_SERVE) - s[COGS]

    rows = [("list", "List revenue", s[LIST], "total"),
            (DISCOUNT, "On-invoice discount", -s[DISCOUNT], "delta"),
            ("invoice", "Invoice revenue", invoice, "total")]
    rows += [(c, label, -s[c], "delta") for c, label in OFF_INVOICE]
    rows.append(("pocket", "Pocket revenue", pocket, "total"))
    rows += [(c, label, -s[c], "delta") for c, label in COST_TO_SERVE]
    rows += [(COGS, "COGS", -s[COGS], "delta"), ("margin", "Pocket margin", margin, "total")]

    out = pd.DataFrame(rows, columns=["step", "label", "amount_cad", "kind"])
    out["pct_of_list"] = out["amount_cad"] / s[LIST]
    return out


def add_row_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Per-transaction pocket revenue, leakage, rates and pocket margin.

    Row-level rates are only for looking at single transactions; group-level rates
    must always come from `waterfall` (ratio of sums).
    """
    out = df.copy()
    off = [c for c, _ in OFF_INVOICE]
    out["pocket_revenue_cad"] = out[LIST] - out[DISCOUNT] - out[off].sum(axis=1)
    out["leakage_cad"] = out[LIST] - out["pocket_revenue_cad"]
    out["pocket_margin_cad"] = (out["pocket_revenue_cad"]
                                - out[[c for c, _ in COST_TO_SERVE]].sum(axis=1) - out[COGS])
    list_nonzero = out[LIST].where(out[LIST] != 0)
    out["discount_rate"] = out[DISCOUNT] / list_nonzero
    out["leakage_rate"] = out["leakage_cad"] / list_nonzero
    return out


def leakage_sources(wf: pd.DataFrame) -> pd.DataFrame:
    """The leakage steps (discount and allowances) ranked by size.

    Columns: label, amount_cad (positive), pct_of_list, share_of_leakage.
    """
    keys = [DISCOUNT] + [c for c, _ in OFF_INVOICE]
    src = wf[wf["step"].isin(keys)].copy()
    src["amount_cad"] = -src["amount_cad"]
    src["pct_of_list"] = -src["pct_of_list"]
    total = src["amount_cad"].sum()
    src["share_of_leakage"] = src["amount_cad"] / total if total else float("nan")
    return src.sort_values("amount_cad", ascending=False)[
        ["label", "amount_cad", "pct_of_list", "share_of_leakage"]].reset_index(drop=True)


def compare_steps(wf_selected: pd.DataFrame, wf_reference: pd.DataFrame) -> pd.DataFrame:
    """Each price deduction / cost-to-serve step as a positive fraction of list revenue.

    COGS is left out: it is a cost, not a price concession, and at ~60% of list revenue
    it would dwarf the few-percent steps this comparison is meant to show.
    """
    delta_a = wf_selected[(wf_selected["kind"] == "delta") & (wf_selected["step"] != COGS)]
    delta_b = wf_reference[wf_reference["kind"] == "delta"].set_index("step")
    out = pd.DataFrame({
        "label": delta_a["label"].values,
        "selected": -delta_a["pct_of_list"].values,
        "reference": -delta_b.loc[delta_a["step"], "pct_of_list"].values,
    })
    out["difference_pp"] = (out["selected"] - out["reference"]) * 100
    return out


def check_against_source(df: pd.DataFrame) -> float | None:
    """Largest gap (CAD) between computed invoice revenue and the source column.

    None if the table has no invoice_revenue_cad column to compare with.
    """
    if "invoice_revenue_cad" not in df.columns:
        return None
    return float((df[LIST] - df[DISCOUNT] - df["invoice_revenue_cad"]).abs().max())
