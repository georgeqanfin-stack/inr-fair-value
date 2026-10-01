# Roadmap to 9/10

Started 1 Oct 2026 from a self-assessed 7.5/10. Fifteen gaps, grouped by kind and
listed in the order they will be done. Each item has a definition of done; an item is
closed only when its tests pass and its result is in the report (even if the result
is "this did not help").

Guiding rule: report what the data say. No item is a licence to search specifications
until the backtest looks better.

| # | Item | Status |
|---|---|---|
| 1 | RBI FX intervention and forward book | **Done (v0.6)** |
| 14 | Version number consistent everywhere | **Done (v0.6)** |
| 3 | Market inputs: forward premium, implied rate differential | Next |
| 2 | Real-time data vintages | Planned |
| 4 | Automate manual and stale inputs | Planned |
| 12 | External benchmark: IMF External Sector Report track record | Planned |
| 13 | Peer currencies: panel anchor for all 19 | Planned |
| 5 | Composite weights tested, not assumed | Planned |
| 6 | Joint uncertainty: whole-pipeline bootstrap | Planned |
| 7 | Nonlinear and time-varying adjustment, structural breaks | Planned |
| 9 | Formal panel cointegration tests, multiple-testing adjustment | Planned |
| 8 | Regime model with time-varying transition probabilities | Planned |
| 10 | FEER: cyclical adjustment and income balance | Planned |
| 11 | Flow identification beyond contemporaneous OLS | Planned |
| 15 | Engineering: lint, types, coverage, data schemas, Docker | Planned |

## Data

**1. RBI intervention (done).** RBI Bulletin Table 4 via the RBIH Data API: spot net
purchases, gross legs, outstanding forward book, 1995 onward, two-month publication
lag. Intervention = spot net + change in forward book (swap-neutral). Reaction
function, absorbed pressure at the FPI-implied price of a dollar (lower bound),
forward book as % of reserves. In the report, note and dashboard.

**3. Market inputs.** Add the RBI inter-bank forward premium (1, 3, 6 months; RBIH
`fw_pre_rn`) as the market's interest differential. Test whether it improves the
BEER's rate term and whether the forward-implied rate differs from the policy-rate
gap. Implied volatility and NDF spreads have no free source; record that as a known gap.
*Done when:* the forward premium is in the dataset with its publication lag, tested in
the BEER and flow model, and the result is reported.

**2. Real-time vintages.** (a) US series from ALFRED (CPI, policy rate, and the
dollar index where vintaged), so US inputs are as first published. (b) Keep every
monthly refresh's data/raw as a dated vintage archive, so India's revisions are
captured from now on. (c) Measure how much revisions move the headline, using
the overlap between archived vintages.
*Done when:* the pipeline can run "as of vintage V", and the report states the
revision effect.

**4. Manual and stale inputs.** Replace the hand-entered MOSPI CPI file with an
automatic source where one exists (RBIH, MOSPI API), keep the manual file as a check,
and flag any divergence. Automate the IMF norm lookup if a stable source exists;
otherwise keep it manual with a freshness gate. Make the BoP nowcast explicit when a
quarter is overdue.
*Done when:* no input needs hand entry in a normal month, or the remaining ones are
gated and documented.

## Validation

**12. IMF benchmark.** Table of the IMF External Sector Report's India assessments
(REER gap and CA gap by year, 2012 onward) against this model's reading as it stood
at each ESR's publication. Report the correlation and the sign agreement.
*Done when:* the track record is in the report and README.

**13. Peer currencies.** Run the panel anchor for all 19 currencies; publish the
cross-section of gaps and check India's rank, as well as whether known episodes
(e.g. Turkey 2018, Brazil 2015) show sensible gaps.
*Done when:* a peer table and chart are in the report and dashboard.

## Method

**5. Composite weights.** Compare equal weights with inverse-variance (from each
component's band) and out-of-sample-performance weights, using the same backtest.
Keep equal weights unless another scheme is better out of sample; report the
headline's sensitivity either way.

**6. Joint uncertainty.** Block bootstrap of the whole pipeline (data residuals,
parameters, norm, elasticities) to produce one corridor that includes model
uncertainty. Compare its coverage with the current corridor.

**7. Nonlinear and time-varying adjustment.** Threshold ECM and ESTAR (large gaps
revert faster), time-varying-parameter ECM (Kalman), Bai-Perron break tests on the
ECM and the anchors. Evaluate out of sample with the same tests as the linear model.

**9. Panel statistics.** Pedroni and Westerlund panel cointegration tests alongside
the Fisher approximation; adjust for the 13 specifications tried (Holm or
Romano-Wolf).

**8. Regimes.** Markov switching with transition probabilities driven by oil, VIX,
FPI and RBI intervention (TVTP). Compare with the constant model by likelihood and
out-of-sample regime classification.

**10. FEER.** Cyclical adjustment of the current account for India's and partners'
output gaps (IMF style), and an income-balance term in the semi-elasticity.

**11. Flow identification.** Local projections of the rupee on FPI shocks, with
global EM fund flows or index rebalancing dates as instruments where data allow;
otherwise a VAR with timing restrictions. Report how far the contemporaneous estimate
moves.

## Engineering

**14. Version number.** One version (package, README, report header).

**15. Tooling.** Ruff and a type checker in CI, test coverage report, schema checks
on cached inputs, Dockerfile for a reproducible environment.
