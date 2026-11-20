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

## Regression Diagnosis (Model 2)

A second page, **Regression Diagnosis**, finds transactions whose price reduction is larger than quantity, customer tier, product, channel, region and month explain (Kauppinen, 2014). It appears in the app's sidebar menu next to the waterfall page.

```bash
streamlit run app/dashboard.py     # then choose "Regression Diagnosis" in the sidebar
python -m pytest -q                # includes the regression tests
```

- **Model:** ordinary least squares on `(list revenue - pocket revenue) / list revenue`, trained on the earliest 80% of transactions and tested on the latest 20%. Performance is reported separately for train and test (R², MAE, RMSE).
- **Page:** model metrics and equation, actual vs predicted scatter, regression drivers with confidence intervals, a table of potential exceptions (filter by customer, product, region), and a selector that shows the Price Waterfall of any chosen transaction.
- **Two independent flags:** *statistical outlier* (residual in the top 5%, adjustable in the sidebar) and *contract policy exception* (on-invoice discount above the contract's approved maximum).
- **Read this first:** the data is synthetic, and a large residual is a statistical deviation to investigate, **not** proof of a pricing mistake or of recoverable profit. Equation, variables, assumptions and limits: [docs/regression_diagnosis.md](docs/regression_diagnosis.md).

## Root Cause Diagnosis and Scenario Simulation (Model 3)

A third page, **Root Cause Simulation**, takes the transactions flagged by the Regression Diagnosis, shows which deduction drives each one, and lets a consultant test "what if the discount were lower?" against the Price Waterfall. It uses the same model settings as the Regression Diagnosis page, so both pages flag the same transactions.

1. **Choose** a flagged transaction (statistical anomaly, contract limit exceeded, or either).
2. **Evidence**: three separate pieces of evidence, never mixed. **Statistical anomaly** is model-based. **Contract limit exceeded** is a rule checked against contract data (whether it was approved is not in the data). Price override is context only.
3. **Root cause**: each of the five deductions compared with the median of its customer-tier peers, with a plain-language summary.
4. **Simulate**: adjust the on-invoice discount, rebate rate, early-payment discount, credit and promotional allowances (or use a quick scenario), and compare original and simulated pocket revenue, pocket margin and both waterfalls.
5. **Portfolio**: apply one rule to every flagged transaction in the current selection and add up the effect.

Everything on the simulation side is **hypothetical**, not recoverable profit: it assumes the customer buys the same quantity at the new price. Rebate and early-payment accruals are contract rates on invoice revenue (as in the data), so they are recomputed when the discount changes. Details and limits: [docs/root_cause_simulation.md](docs/root_cause_simulation.md).

## Repository layout

```
app/dashboard.py          Streamlit page: Price Waterfall
app/pages/                Streamlit pages: Regression Diagnosis, Root Cause Simulation
src/preprocessing.py      integrate the raw tables into one transaction table
src/pricing_analysis.py   waterfall calculation and transaction-level metrics
src/visualization.py      the staircase waterfall chart
src/regression.py         regression diagnosis: dataset, OLS model, residuals, exception flags
src/regression_charts.py  charts for the regression page
src/diagnosis.py          root cause components, evidence, scenario simulation
src/diagnosis_charts.py   charts for the root cause page
tests/                    unit tests
data/                     raw and integrated synthetic data
docs/                     data dictionary, methodology, prototype notes
```

## Status and limits

This is a prototype. The **price waterfall** is descriptive, and the **regression diagnosis** screens for statistical deviations in price reductions; neither proves a pricing mistake. Per-transaction comparisons are against peers, not conclusions: a large order can legitimately earn a bigger discount. The scenario simulation is hypothetical. Price optimization, RAG and AI agents are not implemented. See [docs/prototype.md](docs/prototype.md) and [docs/regression_diagnosis.md](docs/regression_diagnosis.md).
