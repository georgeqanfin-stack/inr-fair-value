# INR/USD Fair Value Model

A point-in-time fair value framework for the Indian rupee, combining a REER
structural gauge, a FEER external-sustainability model, a BEER market model,
Markov-switching regimes, and an error-correction (ECM) forecast test.
Data: RBI DBIE, FRED, World Bank and MOSPI, January 2000 onward.

**Version 0.3** replaces the exploratory notebooks with a tested, reproducible
pipeline in which every number uses only data published at that date. Fixing
the look-ahead reversed the headline result of v0.2; see
[What changed in 0.3](#what-changed-in-03).

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

**Manual inputs** (the refresh warns when they look out of date):

| File | When | Source |
|---|---|---|
| `data/raw/manual/mospi_cpi_2024base.csv` | monthly, after MOSPI's release (~12th) | MOSPI CPI press release, Annexure IV |
| `data/raw/manual/imf_ca_norm_india.csv` | yearly, after the IMF External Sector Report (July) | IMF EBA estimates, Table 1 |
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
| `model_*.csv`, `composite_ect.csv`, `oos_forecasts_*m.csv` | Model outputs and out-of-sample forecasts |

`outputs/latest.txt` names the most recent run. Runs are never overwritten.

## Current reading (run of 1 Oct 2026, data as of Aug 2026)

Spot INR/USD 95.44 (Aug 2026; RBI data to Jun 2026, Jul–Aug from rescaled FRED EXINUS).

| Model | Misalignment | Fair INR/USD | Status |
|---|---|---|---|
| REER panel anchor (19 EMs) | +18.4% | 80.60 | **REER component of the composite**; productivity-based, panel-cointegrated (p = 0.025) |
| REER gap (one-sided HP) | +5.4% | 90.55 | Cyclical gauge |
| REER fundamentals anchor (India only) | +10.1% | 86.64 | Not cointegrated (p = 0.85): reported only |
| FEER, IMF norm path (central; latest −2.0%) | +6.7% | 89.46 | Latest BoP quarter Oct–Dec 2025; 10th–90th percentile +1.2% to +13.6% |
| FEER, NIIP-stabilising norm (−0.4%) | −3.4% | | Alternative norm |
| BEER, current (real INR/USD, DOLS) | +25.8% | 75.89 | Not cointegrated (p = 0.98): descriptive only |
| BEER, total (permanent fundamentals) | +21.5% | 78.55 | Fundamentals at their one-sided HP trends |
| **Composite (panel anchor + FEER)** | **+12.4%** | **84.91** | Positive = INR weaker than fair |

**Fair-value corridor: 79.5 – 90.1** (10th–90th percentile, combining the panel
anchor's parameter band with the FEER norm and elasticity band), against a spot
rate of 95.44. The panel anchor's gap for full-year 2025 was +8.8%; it widened
because the REER fell about 13% during 2026 while the productivity-implied level kept rising.
Filtered P(stress) = 0.14; 12-month-ahead P(stress) = 0.34 (steady state).

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
country-effect uncertainty. Three specifications are reported:

| Spec | Regressors | Years | Productivity coef. (t) | Panel cointegration p |
|---|---|---|---|---|
| **prod** (central) | relative productivity | 1996–2024 | +0.31 (4.4) | 0.025 |
| long | + government consumption, openness | 1996–2024 | +0.29 (4.0) | 0.98 |
| short | + terms of trade | 2007–2023 | +0.15 (0.7) | 1.00 |

Panel cointegration combines per-country ADF tests on the pooled residuals
(Engle-Granger p-values, Fisher / Maddala-Wu). This approximates formal panel tests.
Twelve variants were compared, and only productivity-only DOLS passed, so the result
is suggestive, not conclusive. Because India's country effect is its mean residual,
the anchor measures deviation from India's own fundamentals-adjusted norm. It has no
net-foreign-assets term.

**REER component choice.** All three REER measures run every time;
`[composite] reer_component` picks one (`panel`, `hp` or `anchor`). Composite
backtests: panel anchor 12-month RMSE ratio 1.02, Clark-West p 0.22, α always
negative; HP gap 1.05, p 1.00, α changes sign; India-only anchor 1.37.

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
| MOSPI, Labour Bureau (via the RBIH Data API) | CPI-Combined (base 2012) and back series, CPI-IW (bases 1982, 2001) | Automatic, cached in `data/raw/dbie/` |
| MOSPI | CPI-Combined, 2024 = 100 (from Jan 2025) | Manual, verified: `data/raw/manual/mospi_cpi_2024base.csv` |

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

- The panel anchor has no net-foreign-assets term (no cross-country IIP source yet;
  the IMF's External Wealth of Nations data would add it), and its cointegration
  evidence comes from one specification out of twelve tried.
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
