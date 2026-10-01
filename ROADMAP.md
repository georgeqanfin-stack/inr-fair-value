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
| 3 | Market inputs: forward premium, implied rate differential | **Done (v0.7)** |
| 2 | Real-time data vintages | **Done (v0.8)**; ALFRED live since v0.10 |
| 4 | Automate manual and stale inputs | **Done (v0.9)** |
| 12 | External benchmark: IMF External Sector Report track record | **Done (v0.10)** |
| 13 | Peer currencies: panel anchor for all 19 | **Done (v0.11)** |
| 5 | Composite weights tested, not assumed | **Done (v0.12)** |
| 6 | Joint uncertainty: whole-pipeline bootstrap | **Done (v0.13)** |
| 7 | Nonlinear and time-varying adjustment, structural breaks | **Done (v0.14)** |
| 9 | Formal panel cointegration tests, multiple-testing adjustment | **Done (v0.15)** |
| 8 | Regime model with time-varying transition probabilities | **Done (v0.16)** |
| 10 | FEER: cyclical adjustment and income balance | **Done (v0.17)** |
| 11 | Flow identification beyond contemporaneous OLS | **Done (v0.18)** |
| 15 | Engineering: lint, types, coverage, data schemas, Docker | **Done (v1.0)** |

## Data

**1. RBI intervention (done).** RBI Bulletin Table 4 via the RBIH Data API: spot net
purchases, gross legs, outstanding forward book, 1995 onward, two-month publication
lag. Intervention = spot net + change in forward book (swap-neutral). Reaction
function, absorbed pressure at the FPI-implied price of a dollar (lower bound),
forward book as % of reserves. In the report, note and dashboard.

**3. Market inputs (done).** Result: the forward premium tracks the policy gap
(correlation 0.75) but rose 1.2 points above it in the 2026 sell-off (86th
percentile); UIP slope 0.60 (se 0.44); the spread does not predict next month's move
(t −0.6); a forward-based real rate adds nothing to the BEER (t −0.5). Implied
forwards, the spread and the tests are in the report, note and dashboard.
Original plan: add the RBI inter-bank forward premium (1, 3, 6 months; RBIH
`fw_pre_rn`) as the market's interest differential. Test whether it improves the
BEER's rate term and whether the forward-implied rate differs from the policy-rate
gap. Implied volatility and NDF spreads have no free source; record that as a known gap.
*Done when:* the forward premium is in the dataset with its publication lag, tested in
the BEER and flow model, and the result is reported.

**2. Real-time vintages (done).** Result: RBI revisions between the Excel and API
vintages move the headline in 11 of 266 months, by at most 0.17 pp; checked on every
run. `python -m inrfv.vintages run <rev>` re-runs any committed vintage. ALFRED US CPI
is implemented and tested, and switches on when FRED_API_KEY is set (keyless ALFRED
downloads do not work). Original plan: (a) US series from ALFRED (CPI, policy rate, and the
dollar index where vintaged), so US inputs are as first published. (b) Keep every
monthly refresh's data/raw as a dated vintage archive, so India's revisions are
captured from now on. (c) Measure how much revisions move the headline, using
the overlap between archived vintages.
*Done when:* the pipeline can run "as of vintage V", and the report states the
revision effect.

**4. Manual and stale inputs (done).** CPI 2024=100 now comes from the RBI Bulletin
CPI table (the manual MOSPI file is a check and fallback; 20/20 months match); the
BPM6 BoP table brings Jan–Mar 2026 (the overdue quarter) and later revisions, used
for the revision window only; INR/USD gaps and Sep 2026 come from RBI's daily
reference rates (FRED patch no longer needed); reserves gaps from weekly data. The
2026 IMF norm (−2.3, ESR Table 2.11) was added; the norm gate now fires each August
until the new ESR row is in. No automatic source exists for the IMF norm. Found and
fixed on the way: the conditional FEER used a zero norm when loans were missing.
Original plan: replace the hand-entered MOSPI CPI file with an
automatic source where one exists (RBIH, MOSPI API), keep the manual file as a check,
and flag any divergence. Automate the IMF norm lookup if a stable source exists;
otherwise keep it manual with a freshness gate. Make the BoP nowcast explicit when a
quarter is overdue.
*Done when:* no input needs hand entry in a normal month, or the remaining ones are
gated and documented.

## Validation

**12. IMF benchmark (done).** Nine IMF EBA assessments (2017–2025). The composite
matches the IMF CA model's sign in 9/9 years, 2.9 pp apart on average at publication
(correlation 0.63); the REER component co-moves with the IMF REER-level model (0.79)
but disagrees on sign (IMF mostly "overvalued" until 2025). In the report, note and
dashboard. Original plan: table of the IMF External Sector Report's India assessments
(REER gap and CA gap by year, 2012 onward) against this model's reading as it stood
at each ESR's publication. Report the correlation and the sign agreement.
*Done when:* the track record is in the report and README.

**13. Peer currencies (done).** India ranks 3rd most undervalued of 19 (Sep 2026);
6 of 7 pre-set crisis episodes move as expected (China 2015 does not); across the 11
currencies the IMF assesses, rank correlation with the IMF REER-index model averages
0.83 a year. In the report, note and dashboard. Original plan: run the panel anchor for all 19 currencies; publish the
cross-section of gaps and check India's rank, as well as whether known episodes
(e.g. Turkey 2018, Brazil 2015) show sensible gaps.
*Done when:* a peer table and chart are in the report and dashboard.

## Method

**5. Composite weights (done).** Performance weights settle at 0.50 and match equal
weights (12-month RMSE ratio 0.976 vs 0.977); inverse-variance weights do worse
(1.037); each component alone does worse than the blend. The pre-set rule keeps equal
weights; headline range +12.9% to +14.4%. Original plan: compare equal weights with inverse-variance (from each
component's band) and out-of-sample-performance weights, using the same backtest.
Keep equal weights unless another scheme is better out of sample; report the
headline's sensitivity either way.

**6. Joint uncertainty (done).** Joint bootstrap corridor (Sep 2026: 79.9–86.4; all
draws undervalued). Ex-post coverage 2017–2025: bootstrap 75% (misses one-sided:
real-time overstated undervaluation), end-to-end 100% at twice the width. The
bootstrap is now the headline corridor. Original plan: block bootstrap of the whole pipeline (data residuals,
parameters, norm, elasticities) to produce one corridor that includes model
uncertainty. Compare its coverage with the current corridor.

**7. Nonlinear and time-varying adjustment (done).** Threshold, cubic and TVP ECMs
forecast worse than linear (12m 1.30–1.42); a rolling 10-year ECM is better (0.944,
p 0.08) but not robustly across window lengths (median 0.970), so the linear ECM stays.
No break in the ECM; mean breaks in the composite and FEER around 2009 (the backcast
norm years). Original plan: threshold ECM and ESTAR (large gaps
revert faster), time-varying-parameter ECM (Kalman), Bai-Perron break tests on the
ECM and the anchors. Evaluate out of sample with the same tests as the linear model.

**9. Panel statistics (done).** Bootstrap Pedroni-type and Westerlund tests; Monte
Carlo picks the group ADF (correct size; Westerlund over-rejects). Central p 0.023;
over the 16-spec family Holm 0.25, BH 0.09: suggestive, not conclusive. Original
plan: Pedroni and Westerlund panel cointegration tests alongside
the Fisher approximation; adjust for the 13 specifications tried (Holm or
Romano-Wolf).

**8. Regimes (done).** TVTP with VIX, Brent, FPI and RBI drivers loses to the
constant model out of sample (log score −0.004 to −0.53; AIC/BIC prefer constant);
constant kept. Original plan: Markov switching with transition probabilities driven by oil, VIX,
FPI and RBI intervention (TVTP). Compare with the constant model by likelihood and
out-of-sample regime classification.

**10. FEER (done).** EBA-coefficient cyclical adjustment with point-in-time output gaps
(India gap corr 0.96 with the IMF's; contribution 0.84) and an income-balance term with
an uncertain foreign-currency share. FEER +10.0% -> +13.0%; composite +15.7%; backtest
0.977 -> 0.964. Original plan: cyclical adjustment of the current account for India's and partners'
output gaps (IMF style), and an income-balance term in the semi-elasticity.

**11. Flow identification (done).** Impact between 0 (rupee drives flows) and −0.13
(flows drive the rupee; persists ~5 months); 2SLS with VIX and US-yield instruments
−0.07 (F 21, J p 0.16, not significant). Attribution flow shares are upper bounds.
Original plan: local projections of the rupee on FPI shocks, with
global EM fund flows or index rebalancing dates as instruments where data allow;
otherwise a VAR with timing restrictions. Report how far the contemporaneous estimate
moves.

## Engineering

**14. Version number.** One version (package, README, report header).

**15. Tooling (done).** Ruff (line length 150 for the report text; three documented
exceptions) and mypy clean; 159 tests, 87% coverage, CI fails below 85%; schema rules
for every cached input, a hard gate in the refresh; Dockerfile, built and tested in
CI. Refactoring verified by byte-identical report, note and dashboard. Original plan: ruff and a type checker in CI, test coverage report, schema checks
on cached inputs, Dockerfile for a reproducible environment.
