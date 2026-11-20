# Methodology

## Model 1: Pocket Price Waterfall (implemented)

Per transaction line (CAD):

```
List revenue      L = quantity x list unit price
Invoice revenue   I = L - on-invoice discount
Pocket revenue   PR = I - volume rebate - early payment discount - credit allowance - promo allowance
Pocket margin    PM = PR - cost to serve (freight + handling) - COGS
```

**Aggregation rule:** rates are ratios of sums (leakage rate of a step = sum(step) / sum(L)), never an average of per-transaction ratios. This weights large orders correctly and guarantees that segment waterfalls add up to the total.

**Checks:** computed invoice revenue reconciles with the source column; `L - all deductions - cost to serve - COGS = PM`; segment totals equal overall totals (see `tests/test_waterfall.py`).

**Leakage vs. cost:** price leakage = L - PR (deductions only). Cost to serve and COGS are shown below pocket revenue to reach margin but are not counted as leakage.

## Model 2: Price Leakage Detection (planned)
Rules against contract terms (approved max discount, rebate rate, price override), plus low-margin flags.

## Model 3: Price Dispersion Analysis (planned)
Compare pocket price for the same product across customers after controlling for volume and contract terms.
