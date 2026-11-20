"""Integrate the raw tables into the input file for Model 1 (pocket price waterfall).

Run from the repo root:
    python -m src.preprocessing

Output: data/processed/model1_waterfall_input.csv
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = ROOT / "data" / "processed" / "model1_waterfall_input.csv"

CUSTOMER_COLS = ["customer_id", "customer_tier", "industry", "province",
                 "sales_channel", "relationship_years"]
PRODUCT_COLS = ["product_id", "product_category", "product_differentiation"]


def build_model1_input() -> pd.DataFrame:
    """transactions (main) + adjustments_costs + customer and product attributes."""
    tx = pd.read_csv(RAW_DIR / "transactions.csv")
    adj = pd.read_csv(RAW_DIR / "adjustments_costs.csv")
    cust = pd.read_csv(RAW_DIR / "customers.csv")
    prod = pd.read_csv(RAW_DIR / "products.csv")

    df = tx.merge(adj, on="transaction_id", how="left", validate="1:1")
    df = df.merge(cust[CUSTOMER_COLS], on="customer_id", how="left", validate="m:1")
    df = df.merge(prod.rename(columns={"differentiation": "product_differentiation"})
                  [PRODUCT_COLS], on="product_id", how="left", validate="m:1")

    assert len(df) == len(tx), "row count changed after joins"
    assert not df.isna().any().any(), "missing values after joins"
    return df


if __name__ == "__main__":
    out = build_model1_input()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(out)} rows x {out.shape[1]} columns -> {OUT_PATH}")
