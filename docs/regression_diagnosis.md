# Regression Diagnosis (Model 2)

Based on Kauppinen (2014), who uses regression analysis to investigate pricing variation and potential
price leakage. The question: **which transactions received a bigger price reduction than normal business
factors explain?** The answer is a list of transactions to look at, not a list of mistakes.

> The data is **synthetic**. The model finds **statistical deviations**, not proven pricing mistakes
> and not guaranteed recoverable profit.

## Equation

One observation per transaction line (5,000).

```
reduction rate = b0 + b1 * ln(quantity) + b2 * month number
                 + customer-tier effects + product effects
                 + sales-channel effects + province effects + residual

reduction rate = (list revenue - pocket revenue) / list revenue
residual       = actual reduction rate - predicted reduction rate
```

Pocket revenue is the one the Price Waterfall calculates, so the target equals the waterfall's
"leakage rate" for every row (a test checks this). The model is ordinary least squares
(`statsmodels`). Categorical variables become dummy variables; the first level of each is the baseline
(Customer tier: Large, Province: Alberta, and so on).

| Predictor | Encoding | Why |
|---|---|---|
| Quantity | `ln(quantity)` | larger orders earn proportionally smaller extra discounts |
| Customer tier | dummies | the main legitimate driver of discount size |
| Product | dummies of category (or of product ID, a sidebar option) | list prices and margins differ |
| Sales channel | dummies | direct and distributor terms differ |
| Province | dummies | regional price levels |
| Month | linear month number (1-12) | seasonal drift |

**Month is a trend, not 12 dummies.** The test set is the latest months, so month dummies for those
months would have no training data. A linear trend can be extended to them.

### Deliberately not used as predictors

Pocket revenue, on-invoice discount, rebates and allowances (they build the target), manual price
override (`price_override_used`) and the contract's approved discount limit (kept for the follow-up
investigation), `invoice_id` (not unique, see the README). A test checks the design matrix.

## Train / test

The earliest 80% of transactions (split on a date, so no day is divided) train the model; the latest 20% are a
held-out test set. Both sets are reported separately. The model fitted on the training period scores every
transaction, and the Sample column says whether a transaction was in train or test.

Current results (default settings): test R² 0.80, MAE 1.4 pp, RMSE 2.2 pp; train R² 0.74, MAE 1.5 pp,
RMSE 2.7 pp. Test is slightly better than train only because the later months happen to be less noisy.

What the model finds: customer tier dominates (Strategic about +5.7 pp, Small about -9.8 pp against Large),
doubling the quantity adds about +0.2 pp, and product category and month have no meaningful effect.

## Finding exceptions

- **Statistical outlier**: residual in the top 5% of all residuals (sidebar slider, 1-20%) and above zero. Only
  positive residuals matter here: a bigger reduction than expected.
- **Contract policy exception**: on-invoice discount above the contract's
  `approved_max_on_invoice_discount_rate` x list revenue (1 cent rounding tolerance). Independent of the model.
  On this data there are 75, all with a manual price override, and all 75 also fall in the top 5% of residuals.

The page lists both kinds, with filters for customer, product and region, and lets you pick a transaction
to see its Price Waterfall, discount against its contract limit and whether a price override was used.

## Assumptions and limits

- **Linear and additive**: effects are added up. Interactions (for example tier x quantity) are not modelled.
- **Normal business factors only**: negotiation context, competitive bids, strategic deals and product-cost
  changes are invisible to the model, so a large residual can be legitimate.
- **Residuals are relative**: the top 5% is always flagged by construction; the threshold says how unusual a
  transaction is compared with its peers, not whether it is wrong.
- **Rates are per transaction**, not weighted by revenue, so a small order counts as much as a large one. For
  money impact use the Price Waterfall.
- **Rebates and early-payment discounts are inside the target**, so contract terms that follow customer tier are
  explained by the tier effect, not flagged.
- **Synthetic data**: coefficients describe the simulation, not a real company.
- **Not implemented yet**: price optimization, RAG and AI agents.
