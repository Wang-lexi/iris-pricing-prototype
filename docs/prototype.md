# Prototype notes (draft text for Appendix D)

*Written so it can be copied into the Draft 2 report's "D. Prototype" appendix. Numbers are from the synthetic data and were computed from `data/processed/model1_waterfall_input.csv`.*

## What it is

A Streamlit page that shows the **price waterfall** of a B2B manufacturer, from list revenue to pocket margin, and lets a user drill from the whole company to one product to one transaction.

- Live demo: https://iris-pricing-prototype.streamlit.app
- Code: https://github.com/Wang-lexi/iris-pricing-prototype
- It maps to the first workstream (price leakage and dispersion analysis): list, invoice and pocket price gaps.

## How to run

```bash
pip install -r requirements.txt
streamlit run app/dashboard.py
python -m pytest -q      # tests
```

Data: synthetic, six simulated sources integrated into one transaction table (see `docs/data_dictionary.md`). No client data is used or stored.

## What it does

1. **Company overview:** waterfall for all transactions, four headline numbers, and the biggest source of leakage.
2. **Product:** the same waterfall for one product, with its leakage rate next to the company's.
3. **Transaction detail:** one transaction's waterfall, the customer's profile (industry, province, tier, channel, years as customer, revenue band, payment terms), and how its discount and leakage compare with the product's other transactions. Transactions are listed with the highest leakage first.

Filters (customer tier, industry, province, channel, product category) apply to all three steps. Every number is a plain calculation, so every figure can be explained step by step (glass-box).

## What it does not do

- It does not check transactions against **contract terms**, so it cannot say that a discount broke a rule. It only shows where money leaves and which transactions look unusual compared with their peers.
- It does not model **price dispersion** (same product, different customers) with volume controls.
- It uses **synthetic** data and runs outside Abacus.AI. It has not been tested on real client data.
- It has no what-if or price recommendation.

## What it taught us (on the synthetic data; descriptive, not causal)

- Price leakage is **$14.01M, 12.05% of list revenue** ($116.26M list, $102.25M pocket revenue). Pocket margin is $32.41M.
- **On-invoice discount is the largest source: 9.0% of list, about 75% of all leakage.** Volume rebates add 2.7%; early-payment discount, credit and promotional allowances together add about 0.3%.
- Leakage rises with **customer tier**: Strategic 20.4%, Large 14.9%, Mid-Market 9.0%, Small 5.5%.
- By industry it ranges from 10.4% (Industrial Distribution) to 13.6% (Food Processing); by channel 11.9% (Direct) to 12.2% (Distributor); by product category only 11.7% to 12.2%. So **who the customer is explains more than what they buy**.
- Transactions with the price-override flag leak more (13.7% vs 11.9%); 11.1% of transactions use an override.
- At transaction level, one transaction (TX-04457) leaks 41.6% of list revenue through a 36.7% discount; the page shows how far such a case sits from its product's median.

## Limits of the evidence

- The data is simulated, so the patterns above show that the tool works, not how a real client behaves.
- Each product has about 100 transactions, so transaction-level comparisons rest on small samples.
- A large order can legitimately earn a bigger discount; peer comparison is a starting point for investigation, not a verdict.

## Verification

16 automated tests check that the waterfall reconciles with the source columns, every step adds up to pocket margin (whole data and a single transaction), group totals add up to the overall total, and the chart's bars sit at the correct heights. The integration of the six tables is described in `docs/data_dictionary.md`.

## To do before submission

- Add the skill file or `agent.md` (scope, triggers, success criteria) that the Draft 2 guide asks for.
- Copy the prototype and these notes into the group repository, where the Draft 2 report must be committed.
