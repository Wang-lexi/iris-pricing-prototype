"""Integrate tables into the input for the pocket price waterfall.

Command line (rebuilds the processed file from data/raw):
    python -m src.preprocessing

Also used by the Streamlit page to integrate uploaded files. Tables are
recognised by their columns, not their file names.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = ROOT / "data" / "processed" / "model1_waterfall_input.csv"

CUSTOMER_COLS = ["customer_id", "customer_tier", "industry", "province",
                 "sales_channel", "relationship_years"]
PRODUCT_COLS = ["product_id", "product_category", "product_differentiation"]


def classify_tables(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Map {filename: DataFrame} to {role: DataFrame} by looking at the columns.

    Roles: integrated, transactions, adjustments, customers, products.
    Files that match no role are ignored. Two files with the same role raise.
    """
    roles: dict[str, pd.DataFrame] = {}
    for name, df in tables.items():
        cols = set(df.columns)
        if {"list_revenue_cad", "cogs_total_cad"} <= cols:
            role = "integrated"
        elif {"transaction_id", "list_revenue_cad"} <= cols:
            role = "transactions"
        elif {"transaction_id", "volume_rebate_accrual_cad"} <= cols:
            role = "adjustments"
        elif {"customer_id", "customer_tier"} <= cols:
            role = "customers"
        elif {"product_id", "product_category"} <= cols:
            role = "products"
        else:
            continue
        if role in roles:
            raise ValueError(f"More than one '{role}' file uploaded (see '{name}').")
        roles[role] = df
    return roles


def integrate(roles: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """transactions (main) + adjustments + optional customer / product attributes."""
    if "integrated" in roles:
        return roles["integrated"].copy()
    for needed in ("transactions", "adjustments"):
        if needed not in roles:
            raise ValueError(
                f"No '{needed}' table found. Upload either one integrated file, or at least "
                "a transactions file and an adjustments/costs file.")

    tx = roles["transactions"]
    try:
        df = tx.merge(roles["adjustments"], on="transaction_id", how="left", validate="1:1")
        if "customers" in roles and "customer_id" in df.columns:
            cust = roles["customers"]
            df = df.merge(cust[[c for c in CUSTOMER_COLS if c in cust.columns]],
                          on="customer_id", how="left", validate="m:1")
        if "products" in roles and "product_id" in df.columns:
            prod = roles["products"].rename(
                columns={"differentiation": "product_differentiation"})
            df = df.merge(prod[[c for c in PRODUCT_COLS if c in prod.columns]],
                          on="product_id", how="left", validate="m:1")
    except pd.errors.MergeError as e:
        raise ValueError(f"Tables could not be joined cleanly (duplicate keys?): {e}") from e

    if len(df) != len(tx):
        raise ValueError("Row count changed after joining tables.")
    return df


def build_model1_input() -> pd.DataFrame:
    """Integrate the CSVs in data/raw and check the result is complete."""
    tables = {p.name: pd.read_csv(p) for p in RAW_DIR.glob("*.csv")}
    df = integrate(classify_tables(tables))
    assert not df.isna().any().any(), "missing values after joins"
    return df


if __name__ == "__main__":
    out = build_model1_input()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(out)} rows x {out.shape[1]} columns -> {OUT_PATH}")
