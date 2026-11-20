import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.preprocessing import load_transactions
from src.pricing_analysis import (
    add_waterfall_columns,
    check_waterfall,
    segment_summary,
    waterfall_totals,
    whale_curve,
)


@pytest.fixture(scope="module")
def df():
    return add_waterfall_columns(load_transactions())


def test_row_count_preserved(df):
    assert len(df) == 5000


def test_waterfall_reconciles_with_source(df):
    gaps = check_waterfall(df)
    assert gaps["invoice_revenue_vs_source"] < 0.01
    assert gaps["list_minus_all_steps_vs_margin"] < 0.01


def test_totals_chain_adds_up(df):
    wf = waterfall_totals(df).set_index("step")["amount_cad"]
    deductions = wf.drop(["list", "invoice", "pocket", "margin"])
    assert wf["list"] + deductions.sum() == pytest.approx(wf["margin"])
    assert wf["list"] + wf["on_invoice_discount_cad"] == pytest.approx(wf["invoice"])


@pytest.mark.parametrize("by", ["customer_tier", "product_category", "month"])
def test_segments_add_up_to_total(df, by):
    seg = segment_summary(df, by)
    assert seg["pocket_revenue_cad"].sum() == pytest.approx(df["pocket_revenue_cad"].sum())
    assert seg["leakage_cad"].sum() == pytest.approx(
        df["list_revenue_cad"].sum() - df["pocket_revenue_cad"].sum())


def test_rate_is_ratio_of_sums_not_mean_of_ratios():
    toy = pd.DataFrame({
        "list_revenue_cad": [1000.0, 10.0],
        "invoice_revenue_calc_cad": [900.0, 5.0],
        "pocket_revenue_cad": [900.0, 5.0],
        "cost_to_serve_cad": [0.0, 0.0],
        "cogs_total_cad": [0.0, 0.0],
        "pocket_margin_cad": [900.0, 5.0],
        "quantity_units": [1, 1],
        "on_invoice_discount_cad": [100.0, 5.0],
        "volume_rebate_accrual_cad": [0.0, 0.0],
        "early_payment_discount_cad": [0.0, 0.0],
        "credit_allowance_cad": [0.0, 0.0],
        "promotional_allowance_cad": [0.0, 0.0],
        "g": ["a", "a"],
    })
    seg = segment_summary(toy, "g")
    assert seg["total_leakage_rate"].iloc[0] == pytest.approx(105 / 1010)  # not (0.1+0.5)/2


def test_whale_curve_ends_at_100_percent(df):
    w = whale_curve(df)
    assert w["cum_margin_pct"].iloc[-1] == pytest.approx(1.0)
    assert w["cum_customers_pct"].iloc[-1] == pytest.approx(1.0)
    assert np.all(np.diff(w["pocket_margin_cad"]) <= 1e-9)
