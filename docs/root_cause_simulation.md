# Root Cause Diagnosis and Scenario Simulation (Model 3)

Connects the Regression Diagnosis (which transactions look unusual?) with the Price Waterfall (where does the
money go?). A consultant picks a flagged transaction, sees which deduction drives it, and tests what pocket
revenue and pocket margin would be under different discount assumptions.

> The data is **synthetic**. Statistical flags are not proof of mistakes, and simulated gains are not
> recoverable profit.

## How the page flows

1. **Pick** an unusual transaction: one the regression flagged (bigger reduction than similar transactions) or whose
   discount is above its contract limit. Both lists come from the Regression Diagnosis page, and the two pages share
   their settings.
2. **See the cause**: which deduction is far above what similar customers get, in plain sentences, with the
   contract limit and any manual price override mentioned.
3. **Try a lower discount** and compare pocket revenue and pocket margin with what actually happened.
4. **Scale it up**: apply one rule to all unusual transactions in the current filter.

Two things are deliberately kept honest rather than hidden:

- A flagged transaction is a **question, not a mistake**. The model cannot see negotiation context, and whether an
  above-limit discount was approved is not in the data.
- Every simulated number is a **what-if, not recovered profit**. It assumes the customer buys the same quantity at
  the new price.

## Root cause: which deduction?

The five deductions between list revenue and pocket revenue (on-invoice discount, volume rebate, early-payment
discount, credit allowance, promotional allowance) are each expressed as a share of list revenue and compared with
the **median of the same customer tier**. Tier is the strongest legitimate driver in the regression, so tier peers
are the fairest comparison. "Above peers" is the difference in percentage points.

- The five amounts add up to list revenue minus pocket revenue, so nothing is counted twice (a test checks this
  for hundreds of transactions).
- A deduction is named the **main driver** only if it is at least **1.5 percentage points** above its peers. That is
  about half the regression's typical error. With this cutoff 9% of ordinary transactions and 82% of statistical
  anomalies get a named driver; a lower bar would name a "driver" for most ordinary transactions.
- On this data the driver is almost always the on-invoice discount, which is 9.0% of list revenue against about
  2.7% for rebates and under 0.3% for everything else.

## Scenario simulation

For one transaction you can change:

| Assumption | Unit | Behaviour |
|---|---|---|
| On-invoice discount | % of list revenue | main lever |
| Volume rebate rate | % of invoice revenue | contract rate |
| Early-payment discount | % of invoice revenue | contract rate |
| Credit allowance | CAD | lump sum, fixed unless changed |
| Promotional allowance | CAD | lump sum, fixed unless changed |

Quick scenarios (they only ever lower the discount): reset; cap at the contract limit; tier-peer median discount;
the discount at which the total reduction equals the model's expected reduction.

```
invoice revenue = list revenue x (1 - discount rate)
rebate          = rebate rate x invoice revenue
early payment   = early-payment rate x invoice revenue
pocket revenue  = invoice revenue - rebate - early payment - credit - promotion
pocket margin   = pocket revenue - freight - handling - COGS
```

**Why rebates move with the discount:** in the data, the rebate is exactly the contract rate times invoice revenue,
and the early-payment discount follows the same rule when it is taken. So a smaller discount raises invoice revenue,
and part of the gain is paid back as a larger rebate accrual. Ignoring this would overstate the benefit. With the
original assumptions the simulator reproduces the existing waterfall exactly (tested on all 5,000 rows).

**Held constant:** quantity, list price, COGS, freight and handling. **Assumed:** the customer buys the same
quantity at the new price. This is the biggest simplification: a customer who pays more may buy less or leave.

## Portfolio view

One rule is applied to every flagged transaction in the current filter:

- **Contract limit exceeded:** discount capped at the approved maximum.
- **Statistical anomaly:** the discount is cut by a chosen share (default 50%) of the unexplained reduction
  (residual x list revenue), never by more than the discount itself.
- **Either flag:** the larger of the two cuts per transaction, never the sum, so nothing is counted twice.

On the default settings: capping the 75 contract-limit cases cuts about 196K CAD of discount and adds about 189K CAD
of pocket revenue (7K CAD is paid back through rebate accruals). That is 0.19% of the company's pocket revenue,
and it is hypothetical.

## Limits

- No demand response: a higher price may lose volume.
- "Expected reduction" comes from a linear model on synthetic data; it is a benchmark, not a target price.
- Tier peers ignore product, quantity and channel; the regression handles those, the component comparison does not.
- Only the on-invoice discount drives the portfolio scenarios. Rebates, early-payment discounts, credits and
  promotions are only changed by hand in the single-transaction simulator.
- Whether a flagged discount was approved, negotiated or a pricing error cannot be known from this data.
