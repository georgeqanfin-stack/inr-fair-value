# INR/USD Fair Value Model

A point-in-time fair value framework for the Indian rupee, combining a REER
structural gauge, a FEER external-sustainability model, a BEER market model,
Markov-switching regimes, and an error-correction (ECM) forecast test.
Data: RBI DBIE, FRED, World Bank and MOSPI, January 2000 onward.

**Version 0.14.** Version 0.3 replaced the exploratory notebooks with a tested,
reproducible pipeline in which every number uses only data published at that date.
Fixing the look-ahead reversed the headline result of v0.2; see
[What changed in 0.3](#what-changed-in-03). Since then:

| Version | Added |
|---|---|
| 0.4 | RBIH Data API, IMF-style FEER with the IMF norm path, panel REER anchor (19 EMs), official MOSPI CPI, BEER rework |
| 0.5 | Monthly refresh with quality gates, dashboard, monthly note, NFA test, flow attribution |
| 0.6 | RBI FX intervention and forward book; [roadmap to 9/10](ROADMAP.md) |
| 0.7 | Forward premia: implied forwards, UIP test, spread over the policy gap, forward-based BEER |
| 0.8 | Data vintages: revision check on every run, past-vintage runner, ALFRED US CPI (with a FRED key) |
| 0.14 | Nonlinear/time-varying ECM variants and break tests; linear ECM kept (rolling not robust) |
| 0.13 | Joint bootstrap corridor (panel, norm, elasticities, CA error, weights) with ex-post coverage check |
| 0.12 | Composite weights tested: equal vs performance vs inverse-variance; equal kept by a pre-set rule |
| 0.11 | Peer currencies: gaps for all 19, India's rank, crisis episodes, cross-section vs the IMF |
| 0.10 | IMF track record: EBA assessments 2017–2025 vs this model; ALFRED US CPI live |
| 0.9 | Automatic inputs: CPI 2024=100 and BPM6 BoP from RBI Bulletin tables, INR/USD from RBI daily rates, reserves gaps from weekly data; 2026 IMF norm; smarter gates |

## Quick start

```bash
pip install -r requirements.txt
pip install -e .
python -m inrfv.run            # uses cached data in data/raw, writes outputs/runs/<run-id>/
python -m inrfv.refresh        # monthly: re-download everything, check, run, summarise
python -m pytest               # 70 tests, ~90 s
```

Optional: copy `.env.example` to `.env` and set `FRED_API_KEY`. Without a key the
pipeline uses FRED's public CSV endpoint. After editing anything in `data/raw` by
hand, run `python -m inrfv.run --write-raw-manifest` to record the new checksums.

## Dashboard

Every run writes `dashboard.html`, and each refresh copies it to
`reports/latest/dashboard.html`. It is a single self-contained file: the run's
numbers are embedded, the charts are drawn in the browser, and only the fonts
load from the internet. It shows:

- the verdict: composite misalignment, fair value, the fair-value range against
  spot, and the stress regime
- INR/USD against composite fair value and its uncertainty range, with 5Y/10Y/all
  ranges, hover readouts and a table of the last 24 months
- misalignment by component (REER component, FEER, composite)
- the filtered stress probability
- every model's reading, its role, and whether its long-run test passes
- the out-of-sample forecast record, input freshness and the run's data notes

It follows the viewer's light or dark theme.

## Monthly note

`note.md` is a one-page summary written for a reader who wants the conclusion,
not the method. It is generated from the run's numbers with fixed wording rules
(no free text), so every figure traces back to `results.json`. It covers:

- **The reading**: misalignment, fair value and its range, and whether the two
  components agree
- **Since the last note** (refresh only): spot, fair value and misalignment,
  with REER and FEER contributions, plus new and revised data grouped by source
- **Risk regime**: current and 12-month stress probability
- **How far to trust it**: the out-of-sample record, and which models fail their
  long-run tests
- **To do**: manual inputs or sources that are overdue

The refresh publishes it as `reports/latest/note.md` and `reports/<YYYY-MM>/note.md`.

## Monthly refresh

`python -m inrfv.refresh` (add `--commit` to commit the result):

1. Backs up `data/raw` and re-downloads every automatic source: FRED, World Bank,
   RBI and MOSPI series via the RBIH Data API, and the BIS panel REERs.
2. Runs quality gates. **Hard failures** restore the backup and exit with code 1:
   cached history that disappeared, or an implausible monthly move in INR/USD, the
   REER or the dollar index. **Warnings** do not stop the run: manual inputs that
   look out of date, RBI source disagreements outside the revision window, and
   stale series.
3. Re-pins `data/raw/MANIFEST.sha256` and runs the pipeline.
4. Writes `refresh_summary.md`: new observations and revisions per file, gate
   results, and how the headline moved since the last published report, split into
   REER and FEER contributions. Copies the report to `reports/latest/` and
   `reports/<as-of month>/`.

Any error restores `data/raw` and exits with code 2.

**Scheduling.** `.github/workflows/monthly-refresh.yml` runs the refresh on the
15th of each month, a few days after MOSPI's CPI release, and can also be started
by hand from the Actions tab. It runs the tests first, commits and pushes only if
every gate passes, and attaches the outputs as an artifact either way. An optional
repository secret `FRED_API_KEY` is used if set.

**Scheduling on this PC (Windows).** To run it locally instead, create a scheduled
task for your user (no admin rights or password needed):

```
powershell -ExecutionPolicy Bypass -File scripts\schedule_monthly_refresh.ps1
```

It runs `scripts\monthly_refresh.cmd` on the 15th at 09:00 (`-Day`, `-Time` to
change), catches up at the next logon if the PC was off, logs to
`outputs\refresh_logs\`, and commits locally without pushing. `-Remove` deletes it.

**Manual inputs** (the refresh warns when they look out of date):

| File | When | Source |
|---|---|---|
| `data/raw/manual/mospi_cpi_2024base.csv` | only if the RBI API lags MOSPI's release (~12th) | MOSPI CPI press release, Annexure IV; otherwise automatic from the RBI Bulletin CPI table |
| `data/raw/manual/imf_ca_norm_india.csv` | yearly, after the IMF External Sector Report (July; the refresh warns from August) | ESR individual economy assessment for India, "EBA Norm" |
| `data/raw/rbi_*.xlsx` | optional | RBI DBIE downloads; merged with the API data |

Each run writes to `outputs/runs/<YYYYMMDD-HHMMSS>/`:

| File | Contents |
|---|---|
| `report.md` | Current reading, regimes, backtest, diagnostics, data warnings, charts |
| `dashboard.html` | Interactive one-page monitor (self-contained; open in any browser) |
| `note.md` | One-page plain-language summary: the reading, what changed, regime risk, reliability, to-dos |
| `results.json` | Every statistic in the report, machine-readable |
| `manifest.json` | Code revision, full config, config hash, SHA-256 of every raw input |
| `panel_reference_month.csv` / `panel_point_in_time.csv` | The data, by reference month and by publication month |
| `model_*.csv` (incl. `model_flows.csv`), `composite_ect.csv`, `oos_forecasts_*m.csv` | Model outputs and out-of-sample forecasts |

`outputs/latest.txt` names the most recent run. Runs are never overwritten.

## Current reading (run of 1 Oct 2026, data as of Sep 2026)

Spot INR/USD 95.41 (Sep 2026 average of RBI's daily reference rates).

| Model | Misalignment | Fair INR/USD | Status |
|---|---|---|---|
| REER panel anchor (19 EMs) | +18.4% | 80.57 | **REER component of the composite**; productivity-based, panel-cointegrated (p = 0.025) |
| REER gap (one-sided HP) | +4.8% | 91.06 | Cyclical gauge |
| REER fundamentals anchor (India only) | +10.1% | 86.62 | Not cointegrated (p = 0.85): reported only |
| FEER, IMF norm path (central; latest −2.3%) | +10.0% | 86.71 | Latest BoP quarter Jan–Mar 2026; 10th–90th percentile +5.2% to +16.8% |
| FEER, NIIP-stabilising norm | −1.6% | | Alternative norm |
| BEER, current (real INR/USD, DOLS) | +25.2% | 76.23 | Not cointegrated (p = 0.98): descriptive only |
| BEER, total (permanent fundamentals) | +21.5% | 78.54 | Fundamentals at their one-sided HP trends |
| **Composite (panel anchor + FEER)** | **+14.1%** | **83.59** | Positive = INR weaker than fair |

**Fair-value corridor: 79.9 – 86.4** (10th–90th percentile of a joint bootstrap
of the panel parameters, the FEER norm and elasticities, current-account
measurement error and the model weights), against a spot rate of 95.41. All 2,000
draws say the rupee is undervalued. The reading rose from +12.4% (August, previous data) mainly through
the FEER: the Jan–Mar 2026 quarter (a US$6.5 bn current-account surplus) and the
IMF's 2026 norm (−2.3% of GDP, from −2.0%) both enter from July 2026.

**The ECM is close to the benchmark but not significantly better.** Out of sample
(2010–2025), at 12 months the composite's RMSE is 2.3% below a random walk with
drift (ratio 0.977). That is the first configuration to beat drift on RMSE, but
the Clark-West p-value is 0.13, so the improvement is not statistically significant. With the
panel anchor, the error-correction coefficient has the right sign in every
out-of-sample window (−0.82 to −0.26 at 12 months), which the HP-based composite did
not (−0.22 to +0.15, Clark-West p = 1.00). Treat the misalignment figures as
valuation gauges, not as a timing signal.

## What changed in 0.3

| Problem in v0.2 | Fix |
|---|---|
| REER trend from a two-sided HP filter over the full sample (future data in every historical fair value) | One-sided recursive HP; the ex-post trend is kept only for reference |
| Markov *smoothed* probabilities and full-sample parameters in the ECM | Filtered probabilities from models re-estimated on data public at each date |
| Expanding-window training rows whose 12-month targets ended after the forecast date | Training uses only fully realised targets (`s + h <= t`) |
| FEER oil elasticity and Brent norm estimated on the full sample | Estimated on quarters already published |
| BEER fair value = full-sample in-sample fit | Expanding-window regression |
| "Strict" GDP lag of 3 months on annual data stamped 1 January (≈15 months early) | GDP public 7 months after year end; nominal INR GDP extrapolated from published years only |
| DXY backfill spliced two different indices, creating a +15.6% jump in Jan 2006 | Ratio splice on the 2006 overlap (seam move now −2.4%) |
| BEER cointegration judged with ordinary ADF p-values (reported p = 0.013) | Engle-Granger with MacKinnon critical values (p = 0.32) |
| Johansen rank = count of all rejections | Sequential trace test |
| Markov forecast used `regime_transition[to, from]` untransposed (12-month P(stress) 0.65) | Row-stochastic matrix with validation (0.31 for the same inputs) |
| 92% hit rate and "information ratio 3.99" on overlapping returns, no benchmark | Random walk with drift, Clark-West, Diebold-Mariano, OOS R², Hodrick (1992) SEs, non-overlapping regressions, naive-baseline hit rate |
| "India repo rate" was `INTDSRINM193N`, the IMF discount rate, gap-filled with the call rate | Overnight call rate (matches Fed funds), or an RBI repo file if provided |
| CPI splice mixed a ratio method and a YoY method | Single ratio splice over the Jan–Mar 2025 overlap; flat MOSPI months flagged |
| Parsers read RBI columns by position (re-running notebook 01 on current files reads INR/SDR as INR/USD) | Parsers find columns by header text and fail loudly |
| Dashboard hardcoded α = −0.450 and reported "CALM, actionable" when P(stress) was NaN | All numbers computed from the run; missing values shown as n/a |
| FRED API key hardcoded in notebooks | Environment variable / `.env`; key removed from all notebooks and checkpoints |

The legacy ECT's apparent 12-month predictability (α = −0.45) came from the
two-sided HP filter. Swapping only that filter into the corrected pipeline
restores α ≈ −0.46; with the one-sided filter α ≈ +0.02 (Hodrick t = 0.05).

## Methodology

Sign convention: positive misalignment = INR undervalued (weaker than fair).
Every assumption is in [`config/default.toml`](config/default.toml).

**Point-in-time data.** `panel_reference_month` holds values by the month they
refer to. `panel_point_in_time` holds what was public at each month-end, using
the publication lags in the config: INR/USD, DXY, Brent, VIX, rates and reserves 0;
REER, CPI and trade 1; monthly FPI/FDI 2; quarterly BoP 6 months after the quarter
start; annual World Bank data 7 months after year end. Revisions are not modelled.

**REER gap.** A one-sided HP trend (λ = 129,600) of RBI's 40-currency REER. An HP
gap mean-reverts by construction, so it measures cyclical deviation, not structural
misalignment.

**REER fundamentals anchor (v0.4).** Dynamic OLS, quarterly, of log REER on
relative productivity (India/world real GDP per capita at PPP, World Bank), log
terms of trade (World Bank) and NFA/GDP. NFA is RBI's net IIP: the BPM6 series from
2018, BPM5 for 2006–17 (the two agree over 2018–21), and the cumulated current
account before that. It is re-estimated each quarter on data public at the time.
Annual data enter only from their publication date: World Bank GDP 7 months after
year end, terms of trade 18 months after. The band comes from the coefficients'
HAC covariance. **Result:** no specification cointegrates. Twelve variants were
tested (world, high-income and US productivity benchmarks, with and without terms
of trade and NFA), with Engle-Granger p between 0.60 and 0.87. Coefficients swing
widely across re-estimations, and NFA has the wrong sign. The productivity
coefficient is consistently positive, at about 0.2. India's productivity relative to
the world has more than doubled since 2005 while the REER stayed between 86 and 108,
so the fundamentals do not pin down the REER level over this sample. The anchor is
reported every run but not used in the composite: a composite built on it forecasts
worse (12-month RMSE ratio 1.37 vs drift). `[composite] reer_component = "anchor"`
switches it in.

**FEER (v0.4).** For each quarter, with data public at its BoP release:

- *Current account*: trailing 4-quarter sum as % of GDP (removes seasonality).
- *Oil adjustment*: net oil imports × (1 − Brent norm / Brent paid), with the norm
  the trailing 5-year mean. This is the part of the oil bill due to prices above
  normal, holding volumes fixed. Underlying CA = CA + oil adjustment.
- *Semi-elasticity*: the IMF EBA formula −(η_x·X/GDP + η_m·M/GDP)/100 with
  η_x = 0.46 and η_m = 0.25 (IMF EBA-Lite 3.0) and India's gross goods and services
  trade shares. This is about −0.16 pp of GDP per 1% REER, where v0.2 assumed −0.267.
- *Norms*: central is the **IMF norm path**, India's EBA current-account norms
  as the IMF published them, from −3.4% (2013 Article IV) through −4.2%
  (2015–16) to −2.0% (2025). Each applies from its publication month (data file
  `data/raw/manual/imf_ca_norm_india.csv`, sourced row by row from the IMF EBA
  estimate tables and Article IV staff reports). Quarters before Feb 2013 use the
  earliest norm and are labelled as a backcast. Also reported: a fixed −2.0%, the
  CA that keeps NIIP/GDP constant, n·g/(1+g) (about −0.4% today), and the legacy
  −2.5%. The IMF's own CA-to-REER elasticities in those tables (0.15–0.18) bracket
  this model's −0.16.
- *Band*: 2,000 Monte Carlo draws over the norm (normal, s.e. 0.7) and both
  elasticities (±50% uniform), giving percentiles per quarter and the fair-value corridor.

Cross-check: for FY2024/25 the model gives a CA of −0.59% and an underlying CA of
−0.50%, against the IMF's −0.6% actual and −0.4% cyclically adjusted. The
conditional (financing-adjusted) norm is reported as experimental and kept out of
the composite.

**BEER (v0.4).** Following Clark & MacDonald, the bilateral *real* INR/USD rate
(PPP imposed: log INR/USD minus log CPI India plus log CPI US) is regressed by
dynamic OLS with Newey-West errors on long-run fundamentals: the log broad dollar
index, India-vs-US relative productivity (World Bank GDP per capita, PPP) and the
real interest differential (log Brent in an alternative spec). It is estimated on an
expanding window of published data and re-estimated quarterly. The *current* BEER
uses today's fundamentals; the *total* BEER uses their one-sided HP trends. VIX and
portfolio flows, which drive only the short run, are out of the long-run equation.
Results: dollar +0.72 (t 8.5) and productivity −0.41 (t −8.6), both correctly signed
and stable in sign across re-estimations; the real rate differential adds nothing.
**No specification is cointegrated** (Engle-Granger p 0.78–0.99, Johansen rank 0),
so the BEER gap says where fundamentals would put the rupee, not a level it returns
to. As a predictor, its gap has the right error-correction sign in every
out-of-sample window (12-month Clark-West p = 0.10) but a higher RMSE than drift. It
is reported, not used in the composite.

**Flow attribution (v0.5).** The fair-value models say where the rupee should be;
this asks what moved the spot rate. The monthly INR/USD % change is regressed on net
portfolio (FPI) and direct investment (FDI) flows in US$ bn, and on dollar-index and
Brent % changes (2011 onward, Newey-West errors). Each month's move is split into
those contributions, trend depreciation (the constant) and a residual, summed over
the last 3 and 12 months. Over 2011–2026, each US$1bn of net FPI outflow goes with
about 0.13% rupee weakness (t −4.3). FDI and oil are not significant, and the dollar
index is (+0.46% per 1%). Two checks: the coefficients are re-estimated without the
months being explained, and lead-lag regressions test both directions. Flows predict
next month's rupee move, and the rupee's move predicts next month's flows, so the
contributions are associations, not causes. The analysis is ex post and by reference
month (RBI publishes flows about two months later), so it explains past moves and
does not enter the fair value. It appears in the report, the note and the dashboard.

*RBI intervention (v0.6).* RBI Bulletin Table 4 (via the RBIH Data API, June 1995
onward) gives the RBI's monthly spot net dollar purchases and its outstanding net
forward position. Intervention = spot net purchases + change in the forward book,
so forward sales count when they are made and the two legs of a swap cancel. It is
public two months later. It cannot be a regressor: the RBI sells because the rupee
is under pressure, and a direct regression finds no effect (t 0.2). Instead:

- **Reaction function:** the RBI buys about US$1.2 bn per US$1 bn of net FPI inflow,
  and sells per US$1 bn of outflow (t 4.8). It also sells more as the rupee weakens
  (t −1.6).
- **Absorbed pressure:** each dollar the RBI sold is valued at the market's price of
  a dollar, the FPI coefficient (0.13% per US$1 bn). That gives the move the rupee
  would have made without the RBI. In March–May 2026 the RBI sold US$54 bn, holding
  the rupee about 7 points stronger: absent the RBI, the move would have been about
  12% instead of 5%. The FPI coefficient is net of the RBI's usual response, so the
  absorbed share is a lower bound. `[models.flows] dollar_price` overrides it.
- **Forward book:** net forward sales of US$137 bn in July 2026, 20% of reserves,
  shown on the dashboard as a vulnerability gauge.

**Market pricing (v0.7).** The RBI's inter-bank forward premia (1, 3 and 6 months,
monthly average, % a year, 1993 onward via the RBIH Data API) are the market's
rupee-dollar interest differential. Market data enter with no publication lag, and a
missing month is bridged by the last value. Three uses:

- **Implied forwards:** spot × (1 + premium × months/12). In June 2026 the 6-month
  premium was 3.0%, a forward of about 96.9 against a fair value of 84.9.
- **UIP test:** the premium predicts the depreciation that follows with slope 0.60
  (se 0.44, 3-month). That is consistent with UIP (slope 1) but too imprecise to
  say much.
- **Spread over the policy-rate gap:** the 3-month premium was 1.2 points above
  India's policy rate minus Fed funds in June 2026, higher than 86% of months since
  2000. That points to hedging demand and expected depreciation beyond carry, but
  it does not predict the next month's rupee move (t −0.6).

A forward-based real rate differential was also tested in the BEER (`fwd` spec). It
adds nothing (t −0.5), as the policy-rate differential does not, so the interest
differential does not matter for the BEER whichever way it is measured.

**Data vintages (v0.8).** Point-in-time handling covers publication lags; this covers
revisions.

- *RBI revisions:* the DBIE Excel files and the RBIH Data API are two vintages of the
  same series. Every run re-runs the headline models on a dataset that prefers the
  earlier vintage wherever both exist (`[dbie] mode = "merge_early"`), and compares
  each point-in-time reading. Between the two vintages the RBI revised the BoP
  current account (up to 15%), FDI and loans (up to 35%), monthly FDI and imports.
  The headline moved in 11 of 266 months, by at most 0.17 points (2026, through the
  FEER). Revisions to RBI data matter little for the reading. This is a lower bound,
  since the earlier files are themselves partly revised.
- *Past vintages:* every refresh commits data/raw, so the git history is a dated
  archive of inputs. `python -m inrfv.vintages run <git-rev>` re-runs the full
  pipeline on data/raw as committed at that revision.
- *US CPI:* with a FRED API key, US inflation at each month-end comes from FRED's
  real-time archive (ALFRED), as published then, which also captures the actual
  release calendar. The vintages are cached in data/raw/alfred, and the report states
  how far they differ from the revised series. Without a key, the revised series with
  a one-month lag is used and the report says so.

**External benchmark: the IMF (v0.10).** Each year the IMF's External Balance
Assessment (EBA) assesses India's current account and real exchange rate for the
previous year. India's rows for the 2017–2025 analyses (ESR 2018–2026) were extracted
from the IMF's "EBA estimates" tables into `data/raw/manual/imf_eba_india.csv`
(`scripts/extract_imf_eba.py`). Every run compares them with this model, on the same
sign convention (positive = undervalued):

| This model vs IMF | Same sign | Mean abs. difference at IMF publication | Correlation at publication |
|---|---|---|---|
| Composite vs IMF CA model (CA gap / elasticity) | 9 of 9 years | 2.9 pp (ours 1.5 pp more undervalued) | 0.63 |
| FEER vs IMF CA model | 9 of 9 | 5.0 pp | 0.61 |
| REER component vs IMF REER-level model | 1 of 9 | 11.6 pp | 0.79 |

The IMF's own models disagree about India. Its CA model, which staff assessments rest
on, has found the rupee undervalued every year, and this model agrees on the sign
every year. Its REER regressions mostly found it overvalued until 2025. This model's
REER component moves with them (correlation 0.79) but sits about 12 points lower. The
FEER-vs-IMF-CA pairing is not independent, since the FEER uses the IMF's published
norms. The latest IMF staff assessment (ESR 2026, FY2025/26) puts the REER gap at −8.4%
(range −11.7% to −5.1%), i.e. +8.4% undervalued; this model read +14.3% in July 2026.

**Peer currencies (v0.11).** The panel anchor's pooled fit gives every one of the 19
currencies a point-in-time REER misalignment each month (its own country effect plus
the pooled productivity effect; `model_peers.csv`). Gaps are relative to each
currency's own history, so rankings and movements matter more than levels. In
September 2026 the rupee is the 3rd most undervalued of 19, behind the Turkish lira
and the Korean won.

- *Episodes,* fixed in the config before looking at the results: 6 of 7 move the
  expected way. These are Turkey 2018, Brazil 2015, South Africa 2015, Mexico 2016,
  Mexico's 2023–24 "super peso" (towards overvaluation), and India's 2013 taper
  tantrum. China's Aug 2015 devaluation does not: the renminbi's trade-weighted rate
  stayed near its peak.
- *Against the IMF:* the IMF's EBA assesses 11 of the 19 currencies each year
  (`data/raw/manual/imf_eba_panel.csv`, 2017–2025). The model agrees closely with the
  IMF's REER models: pooled correlation 0.80 with the REER-index model, mean rank
  correlation within a year 0.83 (never below 0.74), and correlation within each
  country over time 0.86. It does not match the IMF's CA model (−0.20), but neither do
  the IMF's own REER models; the IMF's two approaches disagree across countries.

**Regimes.** Two-state Markov switching in the mean and variance of monthly INR
returns, re-estimated every 12 months; filtered probabilities only. Oil × DXY
quadrants use expanding medians.

**REER panel anchor (v0.4, default REER component).** India's coefficients cannot
be pinned down from its own 20 years, so, as in the IMF EBA REER model, they are
estimated on a panel of 19 emerging markets: India, China, Brazil, Mexico,
Indonesia, Turkey, South Africa, Korea, Thailand, Malaysia, the Philippines, Chile,
Colombia, Peru, Poland, Hungary, Czechia, Israel and Romania. Hard pegs, Argentina,
Russia and Taiwan are excluded. The data are the annual BIS broad REER (FRED
`RB<ISO2>BIS`) and World Bank WDI fundamentals. The model is panel dynamic OLS with
country fixed effects and standard errors clustered by country, re-estimated
whenever a new year is published. India's equilibrium = its country effect + pooled
coefficients × its latest fundamentals, with a band from coefficient and
country-effect uncertainty. Four specifications are reported:

| Spec | Regressors | Years | Productivity coef. (t) | Panel cointegration p |
|---|---|---|---|---|
| **prod** (central) | relative productivity | 1996–2024 | +0.31 (4.4) | 0.025 |
| long | + government consumption, openness | 1996–2024 | +0.29 (4.0) | 0.98 |
| short | + terms of trade | 2007–2023 | +0.15 (0.7) | 1.00 |
| prod_nfa | + net foreign assets | 1996–2023 | +0.32 (4.4) | 0.42 |

Panel cointegration combines per-country ADF tests on the pooled residuals
(Engle-Granger p-values, Fisher / Maddala-Wu). This approximates formal panel tests.
Twelve variants were compared, and only productivity-only DOLS passed, so the result
is suggestive, not conclusive. Because India's country effect is its mean residual,
the anchor measures deviation from India's own fundamentals-adjusted norm.

*Net foreign assets* come from the External Wealth of Nations database (Lane &
Milesi-Ferretti, Brookings, 1970–2024), with year-end data entering 16 months
later. They do not help. With net IIP excluding gold (EWN's estimate) the
coefficient is −0.0005 per pp of GDP (t −0.5). With the officially reported IIP it is −0.0007
(t −0.7). Both have the wrong sign, and adding NFA breaks the panel cointegration
check (p 0.42 and 0.25). So `prod_nfa` is reported every run but is not central.
For India the two NFA measures differ sharply (−34% vs −10% of GDP in 2024),
because EWN values foreign holdings of Indian equity at market prices. EWN is used
as one vintage, so its history includes later revisions. Removing `[panel.nfa]`
from the config drops NFA entirely.

**REER component choice.** All three REER measures run every time;
`[composite] reer_component` picks one (`panel`, `hp` or `anchor`). Composite
backtests: panel anchor 12-month RMSE ratio 1.02, Clark-West p 0.22, α always
negative; HP gap 1.05, p 1.00, α changes sign; India-only anchor 1.37.

**Composite weights (v0.12).** The 50/50 weighting of the REER component and the FEER
is tested every run against point-in-time alternatives, through the same backtest. The
rule, set before testing: keep equal weights unless a scheme lowers the 12-month RMSE
ratio by at least 0.01 and has a lower Clark-West p.

| Scheme | REER weight (mean) | 12-month RMSE ratio | Clark-West p | Headline (Sep 2026) |
|---|---|---|---|---|
| Equal (configured) | 0.50 | 0.977 | 0.13 | +14.1% |
| Performance (Bates-Granger, past forecast errors) | 0.50 | 0.976 | 0.13 | +14.4% |
| Inverse variance (uncertainty bands) | 0.14 | 1.037 | 0.53 | +12.9% |
| REER component only | 1 | 1.231 | 0.50 | +18.4% |
| FEER only | 0 | 1.046 | 0.59 | +10.0% |

Weights learned from each component's track record settle at 50/50, so equal weights
stay. Neither component beats the random walk alone, but the combination does. The
headline ranges from +12.9% to +14.4% across the combination schemes.

**Joint uncertainty (v0.13).** The corridor used to join the panel anchor's and the
FEER's 10th–90th percentile bands end to end. Now one bootstrap draws everything
together each month, point in time:
- the panel slope and India's country effect (country-block bootstrap, re-run at
  every re-estimation);
- the IMF norm (its published standard error) and the trade elasticities (±50%);
- current-account measurement error (sd 0.2 pp of GDP);
- the weighting scheme (equal, performance or inverse variance).

To test calibration, every month of 2017–2025 is compared with the fair value as
later re-estimated, using the final panel coefficients and the IMF's own norm for
that year.

| Corridor (nominal 80%) | Coverage, 108 months | Median width |
|---|---|---|
| Joint bootstrap (now the headline) | 75% (all misses below) | 10.7 pp |
| End to end (before) | 100% | 19.4 pp |

The old corridor was about twice as wide as needed. The bootstrap is close to nominal,
but its misses are one-sided: the real-time reading has tended to overstate
undervaluation relative to the later estimate (by about 2 pp on average). The
bootstrap was made the headline after this test, as the one closer to nominal.
Months overlap heavily, so coverage is measured roughly (about nine independent
years). `[uncertainty] headline_corridor = "end_to_end"` restores the old band.

**Nonlinear and time-varying adjustment, breaks (v0.14).** Four variants of the ECM
are re-estimated point in time and scored like the headline. The rule was set before
testing: replace the linear ECM only if a variant lowers the 12-month RMSE ratio by
at least 0.01 and has a lower Clark-West p.

| Variant | 12-month RMSE ratio | Clark-West p |
|---|---|---|
| Linear ECM, expanding window (headline) | 0.977 | 0.13 |
| Threshold ECM (faster reversion outside a band) | 1.340 | 0.55 |
| Cubic, ESTAR approximation | 1.416 | 0.15 |
| Rolling 10-year window | 0.944 | 0.08 |
| Time-varying parameters (Kalman) | 1.299 | 0.52 |

Nonlinear adjustment does not help out of sample. The latest threshold fit has the
textbook shape (gaps beyond ±10% revert, smaller ones do not), but its forecasts are
worse; the cubic term has the wrong sign. The rolling window passes the rule at its
pre-set 120 months. It is not robust, though: across 72–180-month windows the 12-month
ratio runs 0.944–0.983, a median gain of only 0.007. So the linear ECM stays. That
robustness requirement was added after the first results. `[backtest] window_months`
switches to a rolling ECM.

Break tests use sup-Wald with 15% trimming and block-bootstrap p-values. There is no
break in the 12-month ECM (p 0.69) or in the REER component's mean (p 0.30). The
composite's mean breaks in Oct 2009 (14% to 7%, p 0.01), as does the FEER's (2005 and
2009). Both fall in the years the FEER uses the backcast norm (see limitations).

**India CPI (v0.4).** The official MOSPI CPI-Combined, replacing the OECD series:

- 2025 onward: CPI 2024 = 100.
- 2013–2024: CPI 2012 = 100 × MOSPI's linking factor 0.5267.
- 2011–12: MOSPI's 2012-base back series.
- Before 2011: CPI-IW month-on-month changes chained backwards, with the Labour
  Bureau factor 4.63 across the 2006 base change.

Because the 2012→2024 link is an annual average, a single level series cannot
reproduce both the 2012-base inflation published during 2025 and the 2024-base
inflation published from 2026. The models therefore use **inflation as published at
the time**, which matches MOSPI to the hundredth (e.g. Oct 2024 6.21%, Oct 2025
0.25%, Aug 2026 4.82%). The linked level is used only for the long-run PPP test.
`[cpi_india] source = "oecd"` switches back; the report compares the two (inflation
correlation 0.97, mean difference 0.41pp).

**Composite and ECM.** ECT = 0.5 × REER component gap + 0.5 × FEER gap (log). The backtest
regresses h-month INR changes on the ECT using only realised targets and compares
against a random walk with drift.

## Data

| Source | Series | How |
|---|---|---|
| RBI DBIE via the RBIH Data API | INR/USD, REER/NEER (40-currency), reserves, trade, quarterly BoP, monthly FDI/portfolio flows, weighted average call rate | Automatic, cached in `data/raw/dbie/` |
| RBI DBIE Excel downloads | Same series | Optional manual download to `data/raw/rbi_*.xlsx`; merged with the API |
| FRED | US CPI, Fed funds, broad and major dollar indices, VIX, 10Y, Brent, Fed balance sheet, India call rate, OECD India CPI | Automatic, cached in `data/raw/fred/` |
| World Bank | India GDP (current US$), remittances | Automatic, cached in `data/raw/wb_*.csv` |
| RBI Handbook / DBIE (via the RBIH Data API) | Inter-bank forward premia, 1, 3 and 6 months, monthly average | Automatic, cached in `data/raw/dbie/fwd_premium_*.csv` |
| RBI Bulletin Table 4 (via the RBIH Data API) | RBI spot net dollar purchases and sales, outstanding net forward position | Automatic, cached in `data/raw/dbie/rbi_intervention.csv` |
| IMF EBA estimates (2017–2025 analyses) | India's CA norm, CA gap, REER-index and REER-level gaps, CA/REER elasticity | Extracted from the IMF PDFs by `scripts/extract_imf_eba.py` into `data/raw/manual/imf_eba_india.csv` (yearly) |
| FRED / ALFRED | US CPI as published at each date (needs `FRED_API_KEY` in `.env`) | Automatic, cached in `data/raw/alfred/` |
| External Wealth of Nations (Lane & Milesi-Ferretti, Brookings) | Net IIP / GDP for the 19 panel countries | Automatic (latest workbook found on the Brookings page); compact cache `data/raw/ewn/ewn_nfa.csv` |
| MOSPI, Labour Bureau (via the RBIH Data API) | CPI-Combined (base 2012) and back series, CPI-IW (bases 1982, 2001) | Automatic, cached in `data/raw/dbie/` |
| MOSPI via RBI Bulletin (RBIH Data API) | CPI-Combined, 2024 = 100 (from Jan 2025), with the provisional flag | Automatic, cached in `data/raw/dbie/cpi_2024base.csv`; `data/raw/manual/mospi_cpi_2024base.csv` is the check and fallback |
| RBI Bulletin (RBIH Data API) | BoP, BPM6 standard presentation (often a quarter ahead of the typed series) | Automatic, cached in `data/raw/dbie/bop_bpm6.csv`; used for the latest quarters only |
| RBI (RBIH Data API) | Daily INR/USD reference rate, weekly FX reserves | Automatic; monthly averages fill gaps in, and extend, the monthly INR/USD series; weekly reserves fill gaps only |

**RBI data.** DBIE itself has no public API. The pipeline reads DBIE's series from
the [Reserve Bank Innovation Hub](https://github.com/Reserve-Bank-Innovation-Hub/dbie.rbihub.in)'s
public, read-only Data API (`https://data-api.dbie.rbihub.in`), a daily mirror of
DBIE's SDMX series run by an RBI subsidiary. It merges these with any DBIE Excel
files in `data/raw`. Where both sources have a value, the later release wins (RBI
revises recent months). Every run reports each series' coverage, which source was
newer, and any disagreement outside the normal revision window. Missing INR/USD
months, and months after RBI's latest, are filled with FRED's EXINUS rescaled to
RBI's level, and the report says so. `[dbie] mode` in the config switches between
`merge`, `api` and `xlsx`.

See [`data/raw/manual/README.md`](data/raw/manual/README.md) for manual inputs.

## Known limitations (Phase 2 roadmap)

- The panel anchor's cointegration evidence comes from one specification out of
  thirteen tried. Net foreign assets (External Wealth of Nations) were added and
  tested, entered with the wrong sign, and broke the panel check.
- The panel's World Bank fundamentals lag by one to two years, so the equilibrium
  moves in annual steps and the recent gap is driven mostly by the REER itself.
- Before Feb 2013 there is no published IMF norm for India, so the FEER uses the
  earliest one (−3.4%). That makes the 2002–08 surplus years read as a 25–55%
  "undervaluation". The 2017 EBA vintage (assessing 2016) is not available online,
  so the 2016 norm carries forward until Jul 2018.
- The IMF norm and the NIIP-stabilising norm still differ by about 1.6pp today,
  which moves the reading by about 10pp. That is more than the Monte Carlo band.
- A panel model estimating India's norm from structural fundamentals (relative
  income, demographics, oil balance; 19 EMs) was tried and dropped: R² 0.09, no
  correctly-signed significant coefficient. The IMF's norms rely on a much wider
  panel and policy variables this project does not have.
- The FEER has no output-gap adjustment (the IMF adjusts for the domestic and
  partner-country cycle) and no income-balance semi-elasticity.
- Neither the BEER nor the India-only REER anchor is cointegrated on 2001–26 data.
  The rupee has not tracked India's productivity catch-up, and both models record
  that gap rather than an equilibrium the rate returns to.
- No data vintages: revisions to CPI, trade and BoP are not captured.

## Repository layout

```
config/default.toml        all parameters and assumptions
src/inrfv/                 pipeline package (data, models, stats, backtest, report, run)
tests/                     unit, parser and no-look-ahead tests
data/raw/                  inputs + MANIFEST.sha256
data/processed/, outputs/*.png, notebooks/   legacy v0.1–0.2 artefacts (see notebooks/README.md)
outputs/runs/              pipeline runs (git-ignored)
reports/latest/, reports/<YYYY-MM>/   published report and refresh summary (committed)
```
