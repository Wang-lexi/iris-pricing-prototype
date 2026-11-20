import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pricing_analysis import check_against_source, load_input, waterfall


@pytest.fixture(scope="module")
def df():
    return load_input()


def test_matches_source_invoice_revenue(df):
    assert check_against_source(df) < 0.01


def test_steps_add_up_to_margin(df):
    wf = waterfall(df).set_index("step")["amount_cad"]
    deltas = wf.drop(["list", "invoice", "pocket", "margin"])
    assert wf["list"] + deltas.sum() == pytest.approx(wf["margin"])


def test_subtotals(df):
    wf = waterfall(df).set_index("step")["amount_cad"]
    assert wf["list"] + wf["on_invoice_discount_cad"] == pytest.approx(wf["invoice"])
    assert wf["pocket"] == pytest.approx(
        df["invoice_revenue_cad"].sum()
        - df[["volume_rebate_accrual_cad", "early_payment_discount_cad",
              "credit_allowance_cad", "promotional_allowance_cad"]].sum().sum())


def test_subsets_add_up_to_total(df):
    total = waterfall(df).set_index("step")["amount_cad"]
    parts = [waterfall(g).set_index("step")["amount_cad"] for _, g in df.groupby("customer_tier")]
    assert sum(p["pocket"] for p in parts) == pytest.approx(total["pocket"])
    assert sum(p["margin"] for p in parts) == pytest.approx(total["margin"])


# ---- upload / integration -------------------------------------------------
import pandas as pd

from src.preprocessing import RAW_DIR, build_model1_input, classify_tables, integrate
from src.pricing_analysis import prepare_input


def _raw():
    return {p.name: pd.read_csv(p) for p in RAW_DIR.glob("*.csv")}


def test_raw_tables_are_recognised_and_integrate_to_5000_rows():
    roles = classify_tables(_raw())
    assert {"transactions", "adjustments", "customers", "products"} <= set(roles)
    assert len(integrate(roles)) == 5000


def test_uploading_raw_tables_gives_same_waterfall_as_sample(df):
    uploaded, _ = prepare_input(build_model1_input())
    a = waterfall(uploaded).set_index("step")["amount_cad"]
    b = waterfall(df).set_index("step")["amount_cad"]
    assert a["margin"] == pytest.approx(b["margin"])


def test_only_transactions_and_adjustments_still_works():
    raw = _raw()
    roles = classify_tables({k: v for k, v in raw.items()
                             if k in ("transactions.csv", "adjustments_costs.csv")})
    out, _ = prepare_input(integrate(roles))
    assert len(out) == 5000 and "customer_tier" not in out.columns


def test_missing_required_column_gives_clear_error(df):
    with pytest.raises(ValueError, match="cogs_total_cad"):
        prepare_input(df.drop(columns=["cogs_total_cad"]))


def test_optional_columns_default_to_zero(df):
    out, notes = prepare_input(df.drop(columns=["promotional_allowance_cad"]))
    assert (out["promotional_allowance_cad"] == 0).all()
    assert any("promotional_allowance_cad" in n for n in notes)


def test_non_numeric_required_value_is_rejected(df):
    bad = df.copy()
    bad["list_revenue_cad"] = bad["list_revenue_cad"].astype(object)
    bad.loc[0, "list_revenue_cad"] = "abc"
    with pytest.raises(ValueError, match="list_revenue_cad"):
        prepare_input(bad)


def test_two_files_with_same_role_rejected():
    raw = _raw()
    with pytest.raises(ValueError):
        classify_tables({"a.csv": raw["transactions.csv"], "b.csv": raw["transactions.csv"]})
