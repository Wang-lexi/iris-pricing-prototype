# iris-pricing-prototype

B2B Manufacturing Pricing Analytics and Price Leakage Detection Prototype

**Live demo:** https://iris-pricing-prototype.streamlit.app
(Streamlit app on synthetic data. If it shows an error right after an update, the app host may need a restart.)

## What it does

Takes sales transactions of a B2B manufacturer and shows where list-price revenue leaks away on the way to the money the company actually keeps (the *pocket price*).

The page has three steps:

1. **Company overview** – the whole company's price waterfall: list revenue, then on-invoice discount, volume rebate and allowances, down to pocket revenue, freight, handling, COGS and pocket margin. A callout names the biggest source of leakage.
2. **Product** – pick one product and see only its transactions, compared with the company.
3. **Transaction detail** – pick one transaction of that product (the table is sorted by highest leakage first) and see its full waterfall, the customer's profile, and how it compares with the product's other transactions.

Sidebar filters (customer tier, industry, province, sales channel, product category) narrow the data for all three steps.

**Definitions** (per transaction, CAD)

```
Invoice revenue = List revenue - On-invoice discount
Pocket revenue  = Invoice revenue - Volume rebate - Early-payment discount
                  - Credit allowance - Promotional allowance
Pocket margin   = Pocket revenue - Freight - Handling - COGS
Price leakage   = List revenue - Pocket revenue
```

Every percentage is a ratio of sums (for example sum of a step / sum of list revenue), never an average of per-transaction ratios, so large orders weigh more. See [docs/methodology.md](docs/methodology.md).

## Data

All data is **synthetic** (simulated B2B manufacturing, CAD, calendar 2025): 5,000 transaction lines, 100 customers, 50 products. Six simulated sources are described in [docs/data_dictionary.md](docs/data_dictionary.md), together with how they are integrated and the cleaning checks that were run.

- Raw tables: `data/raw/`
- Integrated input for the page: `data/processed/model1_waterfall_input.csv` (rebuild with `python -m src.preprocessing`)

## Run it locally

```bash
pip install -r requirements.txt
streamlit run app/dashboard.py
```

Run the tests:

```bash
python -m pytest -q
```

The tests check that the waterfall reconciles with the source data, that every step adds up to the margin, that groups add up to the total, and that the chart bars sit at the correct heights.

## Repository layout

```
app/dashboard.py          Streamlit page
src/preprocessing.py      integrate the raw tables into one transaction table
src/pricing_analysis.py   waterfall calculation and transaction-level metrics
src/visualization.py      the staircase waterfall chart
tests/                    unit tests
data/                     raw and integrated synthetic data
docs/                     data dictionary, methodology, prototype notes
```

## Status and limits

This is a prototype. It covers the descriptive **price waterfall** only. It does **not** yet check transactions against contract terms (approved maximum discount, rebate rate), and it does not model price dispersion. Per-transaction comparisons are against peers, not conclusions: a large order can legitimately earn a bigger discount. See [docs/prototype.md](docs/prototype.md).
