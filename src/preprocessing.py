"""Load the six synthetic datasets and build one analysis-ready transaction table."""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

TABLES = (
    "transactions",
    "customers",
    "products",
    "contracts_rebates",
    "adjustments_costs",
    "market_data",
)


def load_raw(data_dir: Path = DATA_DIR) -> dict[str, pd.DataFrame]:
    """Read every CSV in `data_dir` into a dict keyed by table name."""
    return {name: pd.read_csv(Path(data_dir) / f"{name}.csv") for name in TABLES}


def build_transactions(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Join transactions with adjustments, customers, products and contracts.

    One row per transaction line. Join keys are validated so that a bad
    extract fails loudly instead of silently duplicating or dropping rows.
    """
    tx = raw["transactions"].copy()
    tx["transaction_date"] = pd.to_datetime(tx["transaction_date"])
    tx["month"] = tx["transaction_date"].dt.to_period("M").dt.to_timestamp()

    df = tx.merge(raw["adjustments_costs"], on="transaction_id", how="left", validate="1:1")
    df = df.merge(
        raw["customers"].drop(columns=["sales_rep_id"]),
        on="customer_id",
        how="left",
        validate="m:1",
    )
    df = df.merge(raw["products"], on="product_id", how="left", validate="m:1")
    df = df.merge(
        raw["contracts_rebates"][
            [
                "contract_id",
                "rebate_rate",
                "approved_max_on_invoice_discount_rate",
                "freight_terms",
            ]
        ],
        on="contract_id",
        how="left",
        validate="m:1",
    )

    if len(df) != len(tx):
        raise ValueError("Join changed the number of transaction rows")
    if df.isna().any().any():
        missing = df.columns[df.isna().any()].tolist()
        raise ValueError(f"Missing values after join in columns: {missing}")
    return df


def load_transactions(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Convenience: raw CSVs -> merged transaction table."""
    return build_transactions(load_raw(data_dir))
