# Data Dictionary

All data is **synthetic** (simulated B2B manufacturing, CAD, calendar year 2025). Raw files live in `data/raw/`; the integrated file for Model 1 lives in `data/processed/`.

## 1. Raw datasets

| Dataset | Simulated source | Grain | Rows | Description |
|---|---|---|---|---|
| `transactions.csv` | ERP (SAP) | transaction line | 5,000 | Quantities, list price, on-invoice discount, invoice revenue, price override flag |
| `customers.csv` | CRM (Salesforce) | customer | 100 | Industry, province, tier, channel, relationship years, payment terms |
| `products.csv` | ERP (SAP) | product | 50 | Category, standard list price, baseline COGS, differentiation, commodity exposure |
| `contracts_rebates.csv` | ERP / contract management | contract (one per customer) | 100 | Rebate rate, approved max on-invoice discount, freight terms |
| `adjustments_costs.csv` | ERP / finance | transaction line | 5,000 | Rebate accrual, early-payment discount, credit and promo allowances, COGS, freight and handling cost |
| `market_data.csv` | external market sources | month | 12 | Synthetic steel, aluminum, polymer, industrial price indices |

## 2. Integration (Model 1 input)

Script: `python -m src.preprocessing` -> `data/processed/model1_waterfall_input.csv` (5,000 rows x 29 columns).

| Step | Join | Key | Relationship |
|---|---|---|---|
| Main table | `transactions` | | |
| 1 | + `adjustments_costs` | `transaction_id` | 1:1 |
| 2 | + `customers` (tier, industry, province, channel, relationship years) | `customer_id` | many:1 |
| 3 | + `products` (category, differentiation) | `product_id` | many:1 |

Not joined: `contracts_rebates` (needed for Model 2 rules, joined on `contract_id` when required) and `market_data` (monthly external index, no direct link to transactions; not used in Model 1).

The script asserts that the row count stays at 5,000 and that no missing values appear after the joins; `validate=` on each merge fails loudly on duplicate keys.

## 3. Cleaning and validation

Checks run on the integrated file. **Result: no rows were removed or changed.**

| Check | Result | Action |
|---|---|---|
| Missing values | 0 | none |
| Duplicate rows (with and without ID columns) | 0 | none |
| Unique `transaction_id`; 1:1 match to adjustments | yes | none |
| All `contract_id`, `customer_id`, `product_id` found in their tables | yes | none |
| Currency | all CAD | no conversion needed |
| Dates | all valid, 2025-01-01 to 2025-12-31 | none |
| Negative values in any numeric column | none | none |
| Whitespace or inconsistent category labels | none | none |
| Arithmetic: list revenue = qty x list price; invoice revenue = list revenue - discount; COGS = unit COGS x qty | hold (max gap < 0.01 CAD) | none |
| Transaction list price vs `products.standard_list_unit_price_cad` | identical | none |
| Zero values | early-payment discount (3,492 rows), credit allowance (4,887), promo allowance (4,854), freight (2,551), volume rebate (15), on-invoice discount (4), `relationship_years` (99) | **kept**: these adjustments are optional by nature, and 0 years means a new customer |

### Unusual values reviewed and kept
These are real business signals, not data errors, so they are left in for analysis:

- **Heavy-tailed order size:** quantity 2 to 400; about 5% of rows are high-value orders by the IQR rule. Kept because large orders are legitimate and must weigh more in totals.
- **Deep discounts:** on-invoice discount rate averages 8.4% (max 37.1%); 25 transactions exceed 30%. Candidates for Model 2, not removed.
- **Invoice below COGS:** 7 transactions have invoice revenue lower than COGS (negative margin before any other deductions). Kept.
- **Unit COGS drift:** transaction unit COGS is 0.999x to 1.256x the baseline in `products.csv` (mean 1.018x), consistent with commodity cost movement.

### Known quirk
`invoice_id` is shared by two transactions that can belong to different customers (2,500 repeated IDs). It is not used as a grouping key.

## 4. Column notes (`model1_waterfall_input.csv`)

| Group | Columns |
|---|---|
| Keys | `transaction_id`, `invoice_id`, `customer_id`, `product_id`, `contract_id`, `sales_rep_id` |
| Transaction | `transaction_date`, `quantity_units`, `currency`, `price_override_used` |
| Price and invoice | `list_unit_price_cad`, `list_revenue_cad`, `on_invoice_discount_cad`, `invoice_revenue_cad` |
| Off-invoice deductions | `volume_rebate_accrual_cad`, `early_payment_discount_cad`, `credit_allowance_cad`, `promotional_allowance_cad` |
| Cost | `unit_cogs_at_transaction_cad`, `cogs_total_cad`, `freight_cost_to_serve_cad`, `handling_cost_to_serve_cad` |
| Customer | `customer_tier`, `industry`, `province`, `sales_channel`, `relationship_years` |
| Product | `product_category`, `product_differentiation` |
