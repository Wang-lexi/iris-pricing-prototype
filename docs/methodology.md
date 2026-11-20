# Methodology

## Model 1: Pocket Price Waterfall (implemented)

Per transaction line (CAD):

```
List revenue      L  = quantity x list unit price
Invoice revenue   I  = L - on-invoice discount
Pocket revenue    PR = I - volume rebate - early payment discount
                         - credit allowance - promotional allowance
Pocket margin     PM = PR - cost to serve (freight + handling) - COGS
```

**Price leakage** = L - PR: discounts, rebates and allowances only. Cost to serve and COGS are shown in the chart to reach margin, but they are costs, not price concessions, so they are not counted as leakage. COGS is also left out of the comparison views for the same reason.

**Aggregation rule.** Rates for any group are ratios of sums:

```
leakage rate of a step    = sum(step) / sum(L)
pocket price realization  = sum(PR) / sum(L)  = 1 - total leakage rate
pocket margin %           = sum(PM) / sum(PR)
```

They are never an average of per-transaction ratios. A $200 order and a $200,000 order must not count equally, and a group's waterfall must add up to the total waterfall. Per-transaction rates are shown only for a single transaction.

**Reconciliation checks** (see `tests/test_waterfall.py`):
- computed invoice revenue equals the source `invoice_revenue_cad` (gap < 0.01 CAD);
- list revenue less every step equals pocket margin, for the whole data and for a single transaction;
- segment totals add up to the overall total;
- the chart's start and end bars have the right heights and no deduction hangs above the start level.

**Chart.** A staircase: the first bar (list revenue) and last bar (pocket margin) stand on zero; each deduction is an orange bar starting where the previous step ended; invoice revenue and pocket revenue appear only as horizontal level lines. The axis starts at zero, so very small steps (a few thousand dollars at company level) are thin.

**Transaction view.** For one transaction the page compares its discount rate, leakage rate and quantity with the median of the same product's transactions, and reports the share of the product's transactions with a lower discount. These are peer comparisons, not findings of wrongdoing.

## Model 2: Price Leakage Detection (planned)
Check each transaction against contract terms (approved maximum on-invoice discount, rebate rate, price override flag) and flag low or negative pocket margin. The contracts table (`contracts_rebates.csv`) is already in `data/raw/` but is not yet joined.

## Model 3: Price Dispersion Analysis (planned)
Compare pocket price of the same product across customers after controlling for volume and contract terms, so that "large customers pay less" is not mistaken for leakage.
