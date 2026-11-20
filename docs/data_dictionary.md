# Data Dictionary

All data is **synthetic** (simulated B2B manufacturing, CAD, calendar 2025). Raw files live in `data/raw/`.

| Dataset | Simulated source | Grain | Rows | Description |
|---|---|---|---|---|
| `transactions.csv` | ERP (SAP) | transaction line | 5,000 | Quantities, list price, on-invoice discount, invoice revenue, price override flag |
| `customers.csv` | CRM (Salesforce) | customer | 100 | Industry, province, tier, channel, relationship years, payment terms |
| `products.csv` | ERP (SAP) | product | 50 | Category, list price, baseline COGS, differentiation, commodity exposure |
| `contracts_rebates.csv` | ERP / contract mgmt | contract (1 per customer) | 100 | Rebate rate, approved max on-invoice discount, freight terms |
| `adjustments_costs.csv` | ERP / finance | transaction line | 5,000 | Rebate accrual, early-pay discount, credit and promo allowances, COGS, freight and handling cost |
| `market_data.csv` | external | month | 12 | Synthetic steel, aluminum, polymer and industrial price indices (not used in Model 1) |

Join keys: `transactions.transaction_id` = `adjustments_costs.transaction_id` (1:1); `customer_id`, `product_id`, `contract_id` (many:1).

## Known quirks
- `invoice_id` is shared by two transactions that can belong to different customers, so it is not used for grouping.
- All transactions are in CAD; no currency conversion is needed.

## Derived fields (Model 1, `src/pricing_analysis.py`)
`invoice_revenue_calc_cad`, `off_invoice_total_cad`, `pocket_revenue_cad`, `cost_to_serve_cad`, `pocket_margin_cad`, `pocket_price_per_unit_cad`.
