"""Tests for root cause diagnosis and scenario simulation."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.diagnosis import (
    COMPONENTS,
    SCOPES,
    baseline_assumptions,
    component_table,
    evidence,
    expected_discount_rate,
    MIN_DRIVER_EXCESS_PP,
    main_driver,
    narrative,
    peer_rates,
    portfolio_scenario,
    simulate_frame,
)
from src.pricing_analysis import COGS, DISCOUNT, LIST, OFF_INVOICE, waterfall
from src.regression import PREDICTED, RESIDUAL, TARGET, fit_model, flag_exceptions, load_dataset

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def flagged():
    result = fit_model(load_dataset(), 0.2)
    return flag_exceptions(result.scored, 0.05)[0]


@pytest.fixture(scope="module")
def breach(flagged):
    """The transaction with the largest contract-limit breach."""
    return flagged[flagged["policy_exception"]].sort_values("excess_discount_pp").iloc[-1]


# ------------------------------------------------------- root cause: components
def test_components_add_up_to_total_deductions_without_double_counting(flagged):
    peers = peer_rates(flagged)
    for tx in flagged["transaction_id"].iloc[:200]:
        row = flagged[flagged["transaction_id"] == tx].iloc[0]
        table = component_table(row, peers)
        assert len(table) == len(COMPONENTS) == 5
        assert table["amount_cad"].sum() == pytest.approx(row[LIST] - row["pocket_revenue_cad"], abs=1e-6)
        assert table["share_of_deductions"].sum() == pytest.approx(1.0)
        assert table["pct_of_list"].sum() / 100 == pytest.approx(row[TARGET])


def test_peer_rates_are_tier_medians():
    df = pd.DataFrame({
        "customer_tier": ["A", "A", "A", "B"], LIST: [100.0] * 4, DISCOUNT: [10.0, 20.0, 30.0, 5.0],
        **{c: [0.0] * 4 for c, _ in OFF_INVOICE}})
    peers = peer_rates(df)
    assert peers.loc["A", DISCOUNT] == pytest.approx(0.20)
    assert peers.loc["B", DISCOUNT] == pytest.approx(0.05)


def test_main_driver_for_a_contract_breach_is_the_on_invoice_discount(flagged, breach):
    table = component_table(breach, peer_rates(flagged))
    driver = main_driver(table)
    assert driver["component"] == "On-invoice discount"
    assert driver["excess_pp"] > 5
    text = " ".join(narrative(breach, table))
    assert "on-invoice discount" in text
    assert "Above the contract limit" in text          # a breach says so
    assert "manual price override was used" in text    # and mentions the override


def test_drivers_are_named_for_anomalies_but_rarely_for_ordinary_transactions(flagged):
    peers = peer_rates(flagged)

    def share_with_driver(rows):
        return np.mean([main_driver(component_table(r, peers)) is not None for _, r in rows.iterrows()])

    ordinary = flagged[~flagged["any_exception"]].sample(300, random_state=0)
    anomalies = flagged[flagged["statistical_exception"]]
    assert share_with_driver(ordinary) < 0.20
    assert share_with_driver(anomalies) > 0.70


def test_the_driver_must_be_clearly_above_peers(flagged):
    peers = peer_rates(flagged)
    for _, r in flagged.head(300).iterrows():
        table = component_table(r, peers)
        driver = main_driver(table)
        assert (driver is None) == (table["excess_pp"].max() < MIN_DRIVER_EXCESS_PP)


def test_narrative_for_a_transaction_within_its_limit_says_so(flagged):
    row = flagged[flagged["statistical_exception"] & ~flagged["policy_exception"]].iloc[0]
    text = " ".join(narrative(row, component_table(row, peer_rates(flagged))))
    assert "Within the contract limit" in text and "Above the contract limit" not in text


# ---------------------------------------- the three kinds of evidence stay apart
def test_statistical_and_policy_evidence_come_from_different_columns(flagged, breach):
    ev = evidence(breach, 0.0244)
    assert ev["Contract limit exceeded"]["flag"] is True
    assert "Rule-based" in ev["Contract limit exceeded"]["text"]
    assert "Model-based" in ev["Statistical anomaly"]["text"]
    assert "not proof" in ev["Statistical anomaly"]["text"]
    assert "not used by the model" in ev["Price override"]["text"]


def test_evidence_flags_follow_the_data(flagged):
    for _, row in flagged[flagged["any_exception"]].head(100).iterrows():
        ev = evidence(row, 0.0244)
        assert ev["Statistical anomaly"]["flag"] == bool(row["statistical_exception"])
        assert ev["Contract limit exceeded"]["flag"] == bool(row["policy_exception"])


def test_a_statistical_anomaly_is_not_automatically_a_policy_breach(flagged):
    only_statistical = flagged["statistical_exception"] & ~flagged["policy_exception"]
    assert only_statistical.sum() == 250 - 75  # flagged by the model, within the contract limit
    assert not flagged.loc[only_statistical, "policy_exception"].any()


# ----------------------------------------------------------------- simulation
def test_baseline_assumptions_reproduce_the_original_waterfall(flagged):
    sim = simulate_frame(flagged)
    assert np.allclose(sim["pocket_revenue_cad"], flagged["pocket_revenue_cad"], atol=1e-6)
    assert np.allclose(sim["pocket_margin_cad"], flagged["pocket_margin_cad"], atol=1e-6)
    assert np.allclose(sim["invoice_revenue_cad"], flagged["invoice_revenue_cad"], atol=0.011)
    assert waterfall(sim).set_index("step").loc["margin", "amount_cad"] == pytest.approx(
        flagged["pocket_margin_cad"].sum())


def test_rebate_and_early_payment_follow_the_contract_rate_on_invoice_revenue(flagged):
    """The data confirms rebate = rate x invoice revenue, so a lower discount raises the accrual."""
    row = flagged[(flagged["volume_rebate_accrual_cad"] > 0)].iloc[[0]]
    sim = simulate_frame(row, discount_rate=0.0)
    rate = row["volume_rebate_accrual_cad"].iloc[0] / row["invoice_revenue_cad"].iloc[0]
    assert sim["volume_rebate_accrual_cad"].iloc[0] == pytest.approx(rate * row[LIST].iloc[0])
    assert sim["volume_rebate_accrual_cad"].iloc[0] > row["volume_rebate_accrual_cad"].iloc[0]


def test_lower_discount_hand_calculation(flagged):
    row = flagged[flagged["transaction_id"] == "TX-00001"]
    sim = simulate_frame(row, discount_rate=0.10).iloc[0]
    r = row.iloc[0]
    invoice = r[LIST] * 0.90
    rebate_rate = r["volume_rebate_accrual_cad"] / r["invoice_revenue_cad"]
    early_rate = r["early_payment_discount_cad"] / r["invoice_revenue_cad"]
    pocket = invoice - invoice * (rebate_rate + early_rate) - r["credit_allowance_cad"] - r["promotional_allowance_cad"]
    assert sim["pocket_revenue_cad"] == pytest.approx(pocket)
    cost = r["freight_cost_to_serve_cad"] + r["handling_cost_to_serve_cad"] + r[COGS]
    assert sim["pocket_margin_cad"] == pytest.approx(pocket - cost)


def test_cogs_cost_to_serve_and_list_revenue_never_change(flagged):
    sim = simulate_frame(flagged, discount_rate=0.02, rebate_rate=0.0, early_rate=0.0,
                         credit_cad=0.0, promo_cad=0.0)
    for col in (LIST, COGS, "freight_cost_to_serve_cad", "handling_cost_to_serve_cad"):
        assert np.allclose(sim[col], flagged[col])


def test_lump_sum_allowances_stay_fixed_when_the_discount_changes(flagged):
    sim = simulate_frame(flagged, discount_rate=0.0)
    assert np.allclose(sim["credit_allowance_cad"], flagged["credit_allowance_cad"])
    assert np.allclose(sim["promotional_allowance_cad"], flagged["promotional_allowance_cad"])


def test_removing_all_deductions_gives_list_revenue(flagged):
    sim = simulate_frame(flagged, discount_rate=0.0, rebate_rate=0.0, early_rate=0.0,
                         credit_cad=0.0, promo_cad=0.0)
    assert np.allclose(sim["pocket_revenue_cad"], flagged[LIST])
    assert np.allclose(sim["reduction_rate"], 0.0)


def test_cutting_the_discount_raises_pocket_revenue_but_less_than_the_cut(flagged, breach):
    row = flagged[flagged["transaction_id"] == breach["transaction_id"]]
    sim = simulate_frame(row, discount_rate=breach["approved_max_on_invoice_discount_rate"]).iloc[0]
    cut = breach[DISCOUNT] - sim[DISCOUNT]
    gain = sim["pocket_revenue_cad"] - breach["pocket_revenue_cad"]
    assert 0 < gain <= cut + 1e-9


def test_expected_discount_preset_hits_the_models_expectation(flagged, breach):
    d = expected_discount_rate(breach)
    sim = simulate_frame(flagged[flagged["transaction_id"] == breach["transaction_id"]],
                         discount_rate=d).iloc[0]
    assert sim["reduction_rate"] == pytest.approx(breach[PREDICTED], abs=1e-6)
    assert d <= breach["discount_rate"]


def test_expected_discount_never_raises_the_discount(flagged):
    normal = flagged[~flagged["any_exception"]].iloc[0]
    assert expected_discount_rate(normal) <= normal["discount_rate"] + 1e-12


# ------------------------------------------------------------------ portfolio
def test_capping_at_the_limit_removes_every_breach(flagged):
    detail, summary = portfolio_scenario(flagged, "Contract limit exceeded", 0.5)
    assert summary["n_affected"] == 75
    cut = detail["discount_cut_cad"]
    new_discount = flagged.set_index("transaction_id").loc[detail["transaction_id"], DISCOUNT].values - cut.values
    limit = (flagged.set_index("transaction_id").loc[detail["transaction_id"],
                                                    "approved_max_on_invoice_discount_rate"]
             * flagged.set_index("transaction_id").loc[detail["transaction_id"], LIST]).values
    assert np.allclose(new_discount, limit)


def test_uplift_is_positive_and_smaller_than_the_discount_cut(flagged):
    for scope in SCOPES:
        _, s = portfolio_scenario(flagged, scope, 0.5)
        assert s["pocket_revenue_change"] > 0
        assert s["pocket_revenue_change"] < s["discount_cut_cad"]
        assert s["accrual_offset_cad"] == pytest.approx(s["discount_cut_cad"] - s["pocket_revenue_change"])


def test_either_scope_uses_the_larger_cut_not_the_sum(flagged):
    _, limit = portfolio_scenario(flagged, "Contract limit exceeded", 0.5)
    _, gap = portfolio_scenario(flagged, "Statistical anomaly", 0.5)
    _, either = portfolio_scenario(flagged, "Either", 0.5)
    assert either["discount_cut_cad"] >= max(limit["discount_cut_cad"], gap["discount_cut_cad"]) - 1e-6
    assert either["discount_cut_cad"] < limit["discount_cut_cad"] + gap["discount_cut_cad"]


def test_closing_none_of_the_gap_changes_nothing_and_more_closes_more(flagged):
    _, none = portfolio_scenario(flagged, "Statistical anomaly", 0.0)
    assert none["n_affected"] == 0 and none["pocket_revenue_change"] == 0
    changes = [portfolio_scenario(flagged, "Statistical anomaly", g)[1]["pocket_revenue_change"]
               for g in (0.25, 0.5, 1.0)]
    assert changes[0] < changes[1] < changes[2]


def test_unflagged_transactions_are_never_touched(flagged):
    detail, _ = portfolio_scenario(flagged, "Either", 1.0)
    assert not detail["transaction_id"].isin(flagged.loc[~flagged["any_exception"], "transaction_id"]).any()


def test_portfolio_rejects_bad_inputs(flagged):
    with pytest.raises(ValueError):
        portfolio_scenario(flagged, "Everything", 0.5)
    with pytest.raises(ValueError):
        portfolio_scenario(flagged, "Either", 1.5)


# ------------------------------------------------------------------- the page
def test_root_cause_page_runs_and_responds_to_the_simulator():
    from streamlit.testing.v1 import AppTest

    entry = ROOT / "app" / "dashboard.py"
    app = AppTest.from_file(str(entry), default_timeout=120).run()
    assert not app.exception
    app.switch_page("pages/3_Root_Cause_Simulation.py").run()
    assert not app.exception

    box = [s for s in app.selectbox if s.label == "Transaction"][0]
    # AppTest wants the option value (the transaction id), not the displayed label
    box.select(box.options[0].split(" · ")[0]).run()
    assert not app.exception
    metrics = {m.label: m for m in app.metric}
    assert metrics["Pocket revenue (what-if)"].delta.startswith("+0 CAD")  # nothing changed yet

    # a quick scenario lowers the discount and raises the simulated pocket revenue
    [b for b in app.button if b.label.startswith("Cap at contract limit")][0].click().run()
    assert not app.exception
    metrics = {m.label: m for m in app.metric}
    assert metrics["Pocket revenue (what-if)"].delta.startswith("+")
    assert not metrics["Pocket revenue (what-if)"].delta.startswith("+0 CAD")

    # reset goes back to the original
    [b for b in app.button if b.label == "Reset to original"][0].click().run()
    metrics = {m.label: m for m in app.metric}
    assert metrics["Pocket revenue (what-if)"].delta.startswith("+0 CAD")

    # moving a slider by hand
    app.slider[0].set_value(2.0).run()
    assert not app.exception

    # portfolio rule and a filter that narrows the data
    [r for r in app.radio if r.label.startswith("Apply to all")][0].set_value("Statistical anomaly").run()
    assert not app.exception
    app.sidebar.multiselect[2].select("Manitoba").run()
    assert not app.exception


def test_model_settings_are_shared_between_the_two_regression_pages():
    from streamlit.testing.v1 import AppTest

    entry = ROOT / "app" / "dashboard.py"
    app = AppTest.from_file(str(entry), default_timeout=120).run()
    app.switch_page("pages/2_Regression_Diagnosis.py").run()
    app.sidebar.slider[1].set_value(0.10).run()  # flag the top 10%
    app.switch_page("pages/3_Root_Cause_Simulation.py").run()
    assert not app.exception
    assert app.sidebar.slider[1].value == pytest.approx(0.10)
