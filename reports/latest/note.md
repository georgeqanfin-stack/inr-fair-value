# USD/INR fair value note, October 2026

Data to October 2026 · run `20261120-220138` · written 20 Nov 2026

## The reading

At 95.52 per dollar, the rupee is substantially undervalued: 15.6% weaker than its composite fair value of 82.64. Allowing for model uncertainty, fair value lies between 78.04 and 85.92, and the spot rate is above the whole range.

The two components agree: the productivity-based REER anchor puts the rupee +18.3% from fair value, and the external-balance model (FEER) +13.0%. Positive means weaker than fair.

## Since the last note

No new month of exchange-rate data since the last note (Oct 2026); the reading is unchanged at +15.6%.

New and revised data this month:

- **US and market data (FRED)**: 1 new observation, now to Nov 2026.

## Risk regime

The regime model reads **calm**: the probability of the high-volatility stress state is 6% (Oct 2026), against a long-run average of 34%. Twelve months ahead it puts the odds at 34%. In stress months the rupee's monthly moves are about 3 times as large as in calm ones (2.4% vs 0.8% standard deviation).

Letting oil, the VIX, portfolio flows or RBI intervention drive the switching odds did not predict the next month better than the regimes' own persistence, so the odds stay constant.

The forward market prices the rupee at 96.94 in six months (premium 3.0% a year, Jun 2026). The premium is +1.2 points over the policy-rate gap, higher than 86% of months since 2000: a sign of hedging demand and expected depreciation beyond carry. Historically the spread has not predicted the next month's move.

## What moved the rupee

From May 2026 to Jul 2026 the rupee weakened 2.4%. Split by a monthly regression on flows and global drivers (points of the move, positive = weaker): trend depreciation +1.5, the dollar +0.6; unexplained +0.6. Each US$1bn of net portfolio outflow goes with about 0.13% rupee weakness. Flows and the rupee feed each other (foreign investors also sell a falling currency), so read these as associations, not causes. Separating cause from effect is hard: if flows drive the rupee within the month the effect is the full 0.13% per US$1bn; if the rupee drives flows it is close to zero; using global risk shocks as instruments gives about 0.07% (54% of it), so the portfolio-flow share above is an upper bound.

Over the same months the RBI sold a net US$28.4 bn, counting forwards. Valued at the market's price of a dollar, that held the rupee about 3.7 points stronger: without it the rupee would have weakened about 6.1% instead of 2.4%, so the RBI absorbed roughly 60% of the pressure (a lower bound). Its net forward sales outstanding stand at US$200 bn, 27% of reserves (Aug 2026).

## How far to trust it

Out of sample (Jun 2010 to Oct 2025), the misalignment signal has a slightly lower forecast error than a random walk with drift at a 12-month horizon (forecast error ratio 0.965, Clark-West p = 0.12), but the difference is not statistically significant. Read the misalignment as a valuation gauge, not a timing signal.

Also: the market-based BEER (+22.4%) fails its long-run test, so it is shown for context only; the India-only REER model fails its long-run test; the productivity anchor passes its long-run test (p 0.023) but not once the 12 specifications tried are allowed for (p 0.25), so its equilibrium is suggestive.

Letting large gaps revert faster, or letting the adjustment drift, did not forecast better out of sample.

Drawing all the uncertainties together (model parameters, the IMF norm, elasticities, data errors and model weights), 100% of 2,000 draws say the rupee is undervalued. Looking back, this 80% range contained the later re-estimated fair value in 66% of months. The range is therefore widened by a factor of 1.23, learned from those misses; tested on years left out of the fit, coverage becomes 78% (applied in real time since Aug 2020 it would have covered 95%, wider than needed).

The equal weighting of the two components was tested against weights learned from each one's track record and from their uncertainty bands; none did clearly better, so the weights stay equal. On their own, neither component beats a random walk at 12 months (ratios 1.23 and 1.02); combined they do (0.965). The headline ranges from +15.0% to +15.8% across weighting schemes.

Among 19 emerging-market currencies on the same model, the rupee is the 2nd most undervalued (Oct 2026). Across countries the model ranks currencies much as the IMF's REER assessments do (average rank correlation 0.83).

Against the IMF's own assessments (2017–2025, its current-account model), this model pointed the same way in 9 of 9 years and was 1.5 points more undervalued on average when the IMF published. The IMF's latest (2025) implies +8.9%.

Data revisions matter little: re-run on the earlier vintage of RBI data, the reading changes by at most 0.5 points in any month (Jun 2026).

## To do

- MOSPI CPI ends Sep 2026 in both the RBI API and data/raw/manual/mospi_cpi_2024base.csv; Oct 2026 should be out. If the API lags, add it from https://www.mospi.gov.in/themes/product/9-consumer-price-index-cpi (Annexure IV).
- Latest BoP quarter is Jan 2026 (quarter start); the next one was due by Oct 2026. Download a fresh BoP file from DBIE or wait for the RBIH API to update.

---

[Dashboard](dashboard.html) · [Full report](report.md) · [What changed](refresh_summary.md)
