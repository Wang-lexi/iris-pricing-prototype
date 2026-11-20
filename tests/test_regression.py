"""Tests for the regression diagnosis module: joins, calculations, model outputs, residuals."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import mean_absolute_error, r2_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pricing_analysis import add_row_metrics, load_input
from src.preprocessing import build_model1_input
from src.regression import (
    FORBIDDEN_PREDICTORS,
    PREDICTED,
    RESIDUAL,
    TARGET,
    chronological_split,
    data_checks,
    design_matrix,
    fit_model,
    flag_exceptions,
    load_dataset,
    predictor_columns,
    prepare_dataset,
)


@pytest.fixture(scope="module")
def data():
    return load_dataset()


@pytest.fixture(scope="module")
def result(data):
    return fit_model(data, test_share=0.2)


# ------------------------------------------------------------------ joins
def test_one_row_per_transaction_and_unique_ids(data):
    assert len(data) == 5000
    assert data["transaction_id"].is_unique


def test_contract_join_is_complete_and_consistent(data):
    assert data["approved_max_on_invoice_discount_rate"].notna().all()
    assert (data["customer_id"] == data["contract_customer_id"]).all()


def test_no_missing_values_in_model_columns(data):
    assert not data[predictor_columns() + [TARGET]].isna().any().any()


def test_processed_file_matches_a_fresh_join_of_the_raw_tables():
    fresh = build_model1_input().set_index("transaction_id").sort_index()
    saved = load_input().set_index("transaction_id").sort_index()
    assert list(fresh.index) == list(saved.index)
    for col in ["customer_tier", "province", "sales_channel", "product_category",
                "list_revenue_cad", "on_invoice_discount_cad"]:
        assert (fresh[col] == saved[col]).all(), col


def test_invoice_id_is_not_unique_and_not_used(data):
    assert data["invoice_id"].duplicated().any()
    assert "invoice_id" not in design_matrix(data).columns
    checks = data_checks(data).set_index("Check")
    assert checks.loc["Duplicate transaction_id", "Result"] == "0"


# ------------------------------------------------------------ calculations
def test_target_is_list_minus_pocket_over_list(data):
    expected = (data["list_revenue_cad"] - data["pocket_revenue_cad"]) / data["list_revenue_cad"]
    assert np.allclose(data[TARGET], expected)
    assert data[TARGET].between(0, 1, inclusive="left").all()


def test_target_agrees_with_the_waterfall_leakage(data):
    """The regression target is the Price Waterfall's leakage rate, row by row."""
    waterfall_rows = add_row_metrics(load_input()).set_index("transaction_id")
    assert np.allclose(data.set_index("transaction_id")[TARGET],
                       waterfall_rows["leakage_rate"])


def test_policy_exception_matches_manual_calculation(data):
    limit_cad = data["approved_max_on_invoice_discount_rate"] * data["list_revenue_cad"]
    manual = data["on_invoice_discount_cad"] > limit_cad + 0.01
    assert (data["policy_exception"] == manual).all()
    assert data["policy_exception"].sum() == 75  # same count as the data validation found
    assert (data.loc[data["policy_exception"], "excess_discount_pp"] > 0).all()


def test_no_leaking_or_investigation_variables_in_the_design_matrix(data):
    for level in ("category", "id"):
        X = design_matrix(data, level)
        for banned in FORBIDDEN_PREDICTORS:
            assert not any(col == banned or col.startswith(banned + "_") for col in X.columns), banned


def test_design_matrix_encodes_categories_as_dummies(data):
    X = design_matrix(data)
    assert not X.isna().any().any()
    assert X["const"].eq(1).all()
    assert "customer_tier_Strategic" in X.columns
    assert "customer_tier_Large" not in X.columns  # first level is the baseline
    assert np.allclose(X["log_quantity"], np.log(data["quantity_units"]))


# ------------------------------------------------------------------- split
def test_split_is_chronological_with_no_overlap(data):
    is_train = chronological_split(data, 0.2)
    assert data.loc[is_train, "transaction_date"].max() < data.loc[~is_train, "transaction_date"].min()
    assert abs((~is_train).mean() - 0.2) < 0.03


# ------------------------------------------------------------ model output
def test_metrics_are_reported_separately_and_are_sensible(result):
    m = result.metrics.set_index("sample")
    assert list(m.index) == ["Train", "Test"]
    assert m.loc["Train", "observations"] + m.loc["Test", "observations"] == 5000
    for sample in ("Train", "Test"):
        assert 0.5 < m.loc[sample, "r_squared"] < 1
        assert 0 < m.loc[sample, "mae"] <= m.loc[sample, "rmse"] < 0.05


def test_metrics_match_an_independent_calculation(result):
    s = result.scored
    test = s[s["sample"] == "Test"]
    m = result.metrics.set_index("sample")
    assert m.loc["Test", "r_squared"] == pytest.approx(r2_score(test[TARGET], test[PREDICTED]))
    assert m.loc["Test", "mae"] == pytest.approx(mean_absolute_error(test[TARGET], test[PREDICTED]))
    assert m.loc["Test", "rmse"] == pytest.approx(np.sqrt(((test[TARGET] - test[PREDICTED]) ** 2).mean()))


def test_model_is_fitted_on_the_training_period_only(result):
    assert int(result.model.nobs) == (result.scored["sample"] == "Train").sum()


def test_known_drivers_have_the_expected_sign(result):
    effect = result.coefficients.set_index("label")["coef_pp"]
    assert effect["Customer tier: Strategic"] > 0       # biggest customers get bigger reductions
    assert effect["Customer tier: Small"] < effect["Customer tier: Mid-Market"] < 0
    assert effect["Quantity: quantity x2"] > 0
    assert (result.coefficients["ci_low_pp"] <= result.coefficients["coef_pp"]).all()
    assert (result.coefficients["coef_pp"] <= result.coefficients["ci_high_pp"]).all()


# --------------------------------------------------------------- residuals
def test_residual_is_actual_minus_predicted(result):
    s = result.scored
    assert np.allclose(s[RESIDUAL], s[TARGET] - s[PREDICTED])
    assert s["transaction_id"].is_unique and len(s) == 5000


def test_training_residuals_average_zero(result):
    train = result.scored[result.scored["sample"] == "Train"]
    assert abs(train[RESIDUAL].mean()) < 1e-9  # OLS with an intercept


def test_flags_the_top_share_of_positive_residuals(result):
    flagged, threshold = flag_exceptions(result.scored, 0.05)
    n = int(flagged["statistical_exception"].sum())
    assert abs(n - 250) <= 2
    assert (flagged.loc[flagged["statistical_exception"], RESIDUAL] >= threshold).all()
    assert (flagged.loc[~flagged["statistical_exception"], RESIDUAL] < threshold).all()
    assert (flagged.loc[flagged["statistical_exception"], RESIDUAL] > 0).all()


def test_threshold_is_adjustable_and_monotone(result):
    counts = [flag_exceptions(result.scored, share)[0]["statistical_exception"].sum()
              for share in (0.01, 0.05, 0.10)]
    assert counts[0] < counts[1] < counts[2]
    with pytest.raises(ValueError):
        flag_exceptions(result.scored, 0)


def test_policy_and_statistical_flags_are_independent(result):
    flagged, _ = flag_exceptions(result.scored, 0.05)
    assert flagged["policy_exception"].sum() == 75
    assert (flagged["any_exception"] == (flagged["statistical_exception"] | flagged["policy_exception"])).all()
    # shrinking the statistical threshold must not change the policy flag
    other, _ = flag_exceptions(result.scored, 0.01)
    assert (flagged["policy_exception"] == other["policy_exception"]).all()


def test_model_recovers_a_planted_effect_and_flags_planted_outliers():
    """Synthetic check of the machinery: known coefficients, 30 planted +10 pp outliers."""
    rng = np.random.default_rng(1)
    n = 3000
    tier = rng.choice(["A", "B"], n)
    qty = rng.integers(2, 400, n)
    dates = pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 364, n), unit="D")
    rate = 0.05 + 0.04 * (tier == "B") + 0.01 * np.log(qty) + rng.normal(0, 0.003, n)
    outliers = rng.choice(n, 30, replace=False)
    rate[outliers] += 0.10
    list_rev = qty * 100.0
    frame = pd.DataFrame({
        "transaction_id": [f"T{i}" for i in range(n)], "transaction_date": dates,
        "customer_tier": tier, "product_category": "P", "sales_channel": "Direct",
        "province": "Ontario", "quantity_units": qty, "list_revenue_cad": list_rev,
        "pocket_revenue_cad": list_rev * (1 - rate),
        "on_invoice_discount_cad": 0.0, "discount_rate": 0.0,
        "approved_max_on_invoice_discount_rate": 0.1,
    })
    res = fit_model(prepare_dataset(frame), 0.2)
    effect = res.coefficients.set_index("label")["coef"]
    assert effect["Customer tier: B"] == pytest.approx(0.04, abs=0.006)
    assert effect["Quantity: quantity x2"] == pytest.approx(0.01, abs=0.002)  # raw ln(quantity) coefficient
    flagged, _ = flag_exceptions(res.scored, 30 / n)
    hit = flagged.loc[flagged["statistical_exception"], "transaction_id"].isin(
        frame.loc[outliers, "transaction_id"]).mean()
    assert hit > 0.8


def test_regression_page_runs_without_errors():
    from streamlit.testing.v1 import AppTest

    # start from the real entry point, as users do, then open the new page
    entry = Path(__file__).resolve().parents[1] / "app" / "dashboard.py"
    app = AppTest.from_file(str(entry), default_timeout=120).run()
    assert not app.exception  # the existing Waterfall page still works
    app.switch_page("pages/2_Regression_Diagnosis.py").run()
    assert not app.exception
    assert len(app.dataframe) >= 3  # data checks, coefficients, exceptions
    # choose a transaction: its Price Waterfall appears
    box = [s for s in app.selectbox if s.label == "Transaction"][0]
    # AppTest wants the option value (the transaction id), not the displayed label
    box.select(box.options[0].split(" · ")[0]).run()
    assert not app.exception
    # a filter that leaves few or no transactions must not crash the page
    app.sidebar.multiselect[2].select("Manitoba").run()
    assert not app.exception
