"""Regression diagnosis (Model 2): which transactions got a bigger price reduction than
normal business factors explain?

Dependent variable (per transaction line):

    reduction_rate = (list revenue - pocket revenue) / list revenue

Pocket revenue is the one used by the Price Waterfall (`pricing_analysis.add_row_metrics`),
so the two modules always agree.

Model (ordinary least squares):

    reduction_rate = b0 + b1 * ln(quantity) + b2 * month_number
                        + customer-tier effects + product effects
                        + sales-channel effects + province effects + residual

Residual = actual - predicted. A large positive residual means a bigger reduction than the
model expected. It is a statistical deviation to investigate, not proof of a pricing mistake.

Never used as predictors (they determine the dependent variable, or are kept for the
follow-up investigation): pocket revenue, on-invoice discount, rebates, allowances,
price_override_used, approved discount limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from .preprocessing import RAW_DIR
from .pricing_analysis import DATA_PATH, DISCOUNT, LIST, add_row_metrics, load_input

CONTRACTS_PATH = RAW_DIR / "contracts_rebates.csv"

TARGET = "reduction_rate"
PREDICTED = "predicted_reduction_rate"
RESIDUAL = "residual"
STD_RESIDUAL = "standardized_residual"

NUMERIC_PREDICTORS = ["log_quantity", "month_number"]
# these are the columns that must never reach the design matrix
FORBIDDEN_PREDICTORS = [
    "pocket_revenue_cad", "leakage_cad", "leakage_rate", "discount_rate", DISCOUNT,
    "invoice_revenue_cad", "volume_rebate_accrual_cad", "early_payment_discount_cad",
    "credit_allowance_cad", "promotional_allowance_cad", "price_override_used",
    "approved_max_on_invoice_discount_rate", "rebate_rate", TARGET,
]

# rounding tolerance when comparing the discount with the contract limit (CAD)
POLICY_TOLERANCE_CAD = 0.01

GROUP_LABELS = {
    "log_quantity": "Quantity",
    "month_number": "Month trend",
    "customer_tier": "Customer tier",
    "product_category": "Product category",
    "product_id": "Product",
    "sales_channel": "Sales channel",
    "province": "Province",
}


# ------------------------------------------------------------------ dataset
def load_dataset(path: Path = DATA_PATH, contracts_path: Path = CONTRACTS_PATH) -> pd.DataFrame:
    """One row per transaction line, with the regression target and contract limits.

    The integrated waterfall table is joined to the contracts on `contract_id`
    (many transactions to one contract). The join can neither add nor drop rows.
    """
    df = add_row_metrics(load_input(path))
    contracts = pd.read_csv(contracts_path)[
        ["contract_id", "customer_id", "approved_max_on_invoice_discount_rate"]
    ].rename(columns={"customer_id": "contract_customer_id"})
    data = df.merge(contracts, on="contract_id", how="left", validate="m:1")
    if len(data) != len(df):
        raise ValueError("Row count changed after joining contracts.")
    return prepare_dataset(data)


def prepare_dataset(data: pd.DataFrame) -> pd.DataFrame:
    """Add target, log quantity, month number and the contract-policy exception flag."""
    out = data.copy()
    out["transaction_date"] = pd.to_datetime(out["transaction_date"])
    out[TARGET] = (out[LIST] - out["pocket_revenue_cad"]) / out[LIST]
    out["log_quantity"] = np.log(out["quantity_units"])
    out["month_number"] = out["transaction_date"].dt.month
    approved_cad = out["approved_max_on_invoice_discount_rate"] * out[LIST]
    out["policy_exception"] = out[DISCOUNT] > approved_cad + POLICY_TOLERANCE_CAD
    out["excess_discount_pp"] = (
        (out["discount_rate"] - out["approved_max_on_invoice_discount_rate"]).clip(lower=0) * 100)
    return out


def data_checks(data: pd.DataFrame) -> pd.DataFrame:
    """Plain-language data checks. Status is OK, WARNING (look at it) or INFO."""
    n = len(data)
    predictors = predictor_columns()
    rows = [
        ("Rows (one per transaction line)", f"{n:,}", "INFO"),
        ("Duplicate transaction_id", str(int(data["transaction_id"].duplicated().sum())),
         "OK" if data["transaction_id"].is_unique else "WARNING"),
        ("Missing values in model columns",
         str(int(data[predictors + [TARGET]].isna().sum().sum())),
         "OK" if not data[predictors + [TARGET]].isna().any().any() else "WARNING"),
        ("Transactions with no matching contract",
         str(int(data["approved_max_on_invoice_discount_rate"].isna().sum())),
         "OK" if data["approved_max_on_invoice_discount_rate"].notna().all() else "WARNING"),
    ]
    mismatch = int((data["customer_id"] != data["contract_customer_id"]).sum())
    rows.append(("Contract belongs to a different customer than the transaction", str(mismatch),
                 "OK" if mismatch == 0 else "WARNING"))
    shared = int(data["invoice_id"].duplicated(keep=False).sum())
    rows.append(("Transactions sharing an invoice_id with another transaction",
                 f"{shared:,} (invoice_id is not used; transaction_id is the key)",
                 "INFO"))
    bad_rate = int(((data[TARGET] < 0) | (data[TARGET] >= 1)).sum())
    rows.append(("Reduction rate outside 0-100%", str(bad_rate), "OK" if bad_rate == 0 else "WARNING"))
    return pd.DataFrame(rows, columns=["Check", "Result", "Status"])


# ------------------------------------------------------------------ design
def predictor_spec(product_level: str = "category") -> tuple[list[str], list[str]]:
    """(numeric predictors, categorical predictors). Product enters as category or as ID."""
    if product_level not in ("category", "id"):
        raise ValueError("product_level must be 'category' or 'id'")
    product = "product_category" if product_level == "category" else "product_id"
    return list(NUMERIC_PREDICTORS), ["customer_tier", product, "sales_channel", "province"]


def predictor_columns(product_level: str = "category") -> list[str]:
    numeric, categorical = predictor_spec(product_level)
    return numeric + categorical


def design_matrix(data: pd.DataFrame, product_level: str = "category") -> pd.DataFrame:
    """Numeric predictors + dummy variables (first level of each category is the baseline)."""
    numeric, categorical = predictor_spec(product_level)
    X = pd.get_dummies(data[numeric + categorical], columns=categorical, drop_first=True,
                       dtype=float)
    return sm.add_constant(X, has_constant="add")


def chronological_split(data: pd.DataFrame, test_share: float = 0.2) -> pd.Series:
    """True for training rows: the earliest dates. The latest `test_share` of rows are test.

    The cut is made on a date, so one day is never split between train and test.
    """
    if not 0 < test_share < 0.5:
        raise ValueError("test_share must be between 0 and 0.5")
    dates = data["transaction_date"].sort_values().reset_index(drop=True)
    cutoff = dates.iloc[len(dates) - round(len(dates) * test_share) - 1]
    return data["transaction_date"] <= cutoff


# ------------------------------------------------------------------- model
@dataclass
class RegressionResult:
    model: object                 # fitted statsmodels OLS results (training period)
    scored: pd.DataFrame          # every transaction with predicted, residual, sample
    metrics: pd.DataFrame         # train and test performance
    coefficients: pd.DataFrame    # effects with confidence intervals
    cutoff_date: pd.Timestamp     # last training day
    product_level: str
    train_rmse: float


def _metrics_row(name: str, y: pd.Series, pred: pd.Series) -> dict:
    return {
        "sample": name,
        "observations": int(len(y)),
        "r_squared": float(r2_score(y, pred)),
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(np.sqrt(mean_squared_error(y, pred))),
    }


def fit_model(data: pd.DataFrame, test_share: float = 0.2,
              product_level: str = "category") -> RegressionResult:
    """Fit OLS on the earliest transactions, then score every transaction."""
    is_train = chronological_split(data, test_share)
    X = design_matrix(data, product_level)
    y = data[TARGET]
    model = sm.OLS(y[is_train], X[is_train]).fit()

    scored = data.copy()
    scored[PREDICTED] = model.predict(X)
    scored[RESIDUAL] = scored[TARGET] - scored[PREDICTED]
    scored["sample"] = np.where(is_train, "Train", "Test")

    metrics = pd.DataFrame([
        _metrics_row("Train", y[is_train], scored.loc[is_train, PREDICTED]),
        _metrics_row("Test", y[~is_train], scored.loc[~is_train, PREDICTED]),
    ])
    train_rmse = float(metrics.loc[0, "rmse"])
    scored[STD_RESIDUAL] = scored[RESIDUAL] / train_rmse
    cutoff = data.loc[is_train, "transaction_date"].max()
    return RegressionResult(model, scored, metrics, _coefficient_table(model, product_level),
                            cutoff, product_level, train_rmse)


def _coefficient_table(model, product_level: str) -> pd.DataFrame:
    """Effects in percentage points of list revenue, with 95% confidence intervals.

    Quantity is shown as the effect of doubling the quantity (coefficient x ln 2); the
    month trend as the effect of one month later; dummies versus their baseline level.
    """
    ci = model.conf_int()
    table = pd.DataFrame({"term": model.params.index, "coef": model.params.values,
                          "ci_low": ci[0].values, "ci_high": ci[1].values,
                          "p_value": model.pvalues.values})
    table = table[table["term"] != "const"].reset_index(drop=True)
    numeric, categorical = predictor_spec(product_level)

    groups, levels, scale = [], [], []
    for term in table["term"]:
        if term in numeric:
            groups.append(GROUP_LABELS[term])
            levels.append("quantity x2" if term == "log_quantity" else "per month later")
            scale.append(np.log(2) if term == "log_quantity" else 1.0)
        else:
            col = next(c for c in categorical if term.startswith(c + "_"))
            groups.append(GROUP_LABELS[col])
            levels.append(term[len(col) + 1:])
            scale.append(1.0)
    table["group"], table["level"], scale = groups, levels, np.array(scale)
    for col in ("coef", "ci_low", "ci_high"):
        table[col + "_pp"] = table[col] * scale * 100
    table["label"] = table["group"] + ": " + table["level"]
    table["significant"] = table["p_value"] < 0.05
    return table


def baseline_levels(data: pd.DataFrame, product_level: str = "category") -> dict[str, str]:
    """The reference level that every dummy-variable effect is measured against."""
    _, categorical = predictor_spec(product_level)
    return {GROUP_LABELS[c]: sorted(data[c].unique())[0] for c in categorical}


def equation_text(result: RegressionResult) -> str:
    """The fitted equation in words, with the main numbers filled in."""
    p = result.model.params
    return (
        f"reduction rate = {p['const']:.4f}"
        f" + {p['log_quantity']:.4f} x ln(quantity)"
        f" + {p['month_number']:+.5f} x month number"
        " + (customer-tier effect) + (product effect) + (sales-channel effect)"
        " + (province effect) + residual")


# -------------------------------------------------------------- exceptions
def flag_exceptions(scored: pd.DataFrame, top_share: float = 0.05) -> tuple[pd.DataFrame, float]:
    """Flag the transactions with the largest positive residuals.

    The threshold is the (1 - top_share) quantile of all residuals, so `top_share=0.05`
    flags the top 5%. Only positive residuals (bigger reduction than expected) are flagged.
    Returns (table with `statistical_exception` and `any_exception`, residual threshold).
    """
    if not 0 < top_share < 1:
        raise ValueError("top_share must be between 0 and 1")
    threshold = float(scored[RESIDUAL].quantile(1 - top_share))
    out = scored.copy()
    out["statistical_exception"] = (out[RESIDUAL] >= threshold) & (out[RESIDUAL] > 0)
    out["any_exception"] = out["statistical_exception"] | out["policy_exception"]
    return out, threshold
