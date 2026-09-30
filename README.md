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
python -m pytest               # 29 tests, ~10 s
```

Optional: copy `.env.example` to `.env` and set `FRED_API_KEY`. Without a key the
pipeline uses FRED's public CSV endpoint. `python -m inrfv.run --refresh`
re-downloads FRED and World Bank data. RBI files must be downloaded by hand from
DBIE (see [Data](#data)). After changing anything in `data/raw`, run
`python -m inrfv.run --write-raw-manifest` to record the new checksums.

Each run writes to `outputs/runs/<YYYYMMDD-HHMMSS>/`:

| File | Contents |
|---|---|
| `report.md` | Current reading, regimes, backtest, diagnostics, data warnings, charts |
| `results.json` | Every statistic in the report, machine-readable |
| `manifest.json` | Code revision, full config, config hash, SHA-256 of every raw input |
| `panel_reference_month.csv` / `panel_point_in_time.csv` | The data, by reference month and by publication month |
| `model_*.csv`, `composite_ect.csv`, `oos_forecasts_*m.csv` | Model outputs and out-of-sample forecasts |

`outputs/latest.txt` names the most recent run. Runs are never overwritten.

## Current reading (run of 1 Oct 2026, data as of Aug 2026)

Spot INR/USD 95.44 (Aug 2026; RBI data to Jun 2026, Jul–Aug from rescaled FRED EXINUS).

| Model | Misalignment | Fair INR/USD | Status |
|---|---|---|---|
| REER gap (one-sided HP) | +5.4% | 90.55 | Cyclical gauge only; the REER component of the composite |
| REER fundamentals anchor | +10.1% | 86.64 | Not cointegrated (Engle-Granger p = 0.85): reported only |
| FEER, IMF norm −2.0% (central) | +6.7% | 89.46 | Latest BoP quarter Oct–Dec 2025; 10th–90th percentile +1.2% to +13.6% |
| FEER, NIIP-stabilising norm (−0.4%) | −3.4% | | Alternative norm: the choice of norm matters more than anything else |
| BEER (expanding window) | +13.8% | 83.83 | Not cointegrated (Engle-Granger p = 0.34): descriptive only |
| **Composite (REER + FEER)** | **+6.0%** | **90.00** | Positive = INR weaker than fair |

**Fair-value corridor: 87.2 – 92.4** (10th–90th percentile over FEER norm and
elasticity uncertainty), against a spot rate of 95.44.
Filtered P(stress) = 0.14; 12-month-ahead P(stress) = 0.34 (steady state).

**The ECM does not forecast.** Out of sample (2013–2025), the composite ECT does
not beat a random walk with drift at any horizon from 1 to 12 months. At 12 months
the RMSE ratio is 1.05 and the Clark-West p-value is 1.00. The 81% directional hit
rate equals the naive "INR always depreciates" baseline. Treat the misalignment
figures as valuation gauges, not as a timing signal.

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
- *Norms*: the IMF EBA norm for India, −2.0% of GDP (s.e. 0.7; 2025 Article IV,
  central); the CA that keeps NIIP/GDP constant, n·g/(1+g) (about −0.4% today);
  and the legacy −2.5% for comparison.
- *Band*: 2,000 Monte Carlo draws over the norm (normal, s.e. 0.7) and both
  elasticities (±50% uniform), giving percentiles per quarter and the fair-value corridor.

Cross-check: for FY2024/25 the model gives a CA of −0.59% and an underlying CA of
−0.50%, against the IMF's −0.6% actual and −0.4% cyclically adjusted. The
conditional (financing-adjusted) norm is reported as experimental and kept out of
the composite.

**BEER.** log INR/USD on log DXY, real overnight-rate differential, FPI/GDP,
log Brent and VIX, estimated on an expanding window.

**Regimes.** Two-state Markov switching in the mean and variance of monthly INR
returns, re-estimated every 12 months; filtered probabilities only. Oil × DXY
quadrants use expanding medians.

**Composite and ECM.** ECT = 0.5 × REER gap + 0.5 × FEER gap (log). The backtest
regresses h-month INR changes on the ECT using only realised targets and compares
against a random walk with drift.

## Data

| Source | Series | How |
|---|---|---|
| RBI DBIE via the RBIH Data API | INR/USD, REER/NEER (40-currency), reserves, trade, quarterly BoP, monthly FDI/portfolio flows, weighted average call rate | Automatic, cached in `data/raw/dbie/` |
| RBI DBIE Excel downloads | Same series | Optional manual download to `data/raw/rbi_*.xlsx`; merged with the API |
| FRED | US CPI, Fed funds, broad and major dollar indices, VIX, 10Y, Brent, Fed balance sheet, India call rate, OECD India CPI | Automatic, cached in `data/raw/fred/` |
| World Bank | India GDP (current US$), remittances | Automatic, cached in `data/raw/wb_*.csv` |
| MOSPI | CPI 2024 = 100 (from Jan 2025) | Manual: `data/raw/manual/mospi_cpi_2024base.csv` |

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

- The REER component is still a filter, not an equilibrium model. The fundamentals
  anchor built to replace it fails cointegration on 2005–26 data (see above). Next
  options: a panel estimate (India plus peers, as in the IMF EBA REER model), or
  importing EBA panel coefficients, since one country's 20-year sample is too short.
- The FEER applies today's IMF norm (−2.0%) to every year back to 2001; norms
  change over time (India ran surpluses in 2001–04, which show up as a 30–40%
  "undervaluation"). The choice between the IMF and NIIP-stabilising norms moves the
  current reading by about 10pp, which is more than the whole Monte Carlo band.
- The FEER has no output-gap adjustment (the IMF adjusts for the domestic and
  partner-country cycle) and no income-balance semi-elasticity.
- The BEER is not cointegrated; re-specify it with DOLS/FMOLS on permanent
  components of the fundamentals.
- No data vintages: revisions to CPI, trade and BoP are not captured.
- India CPI before 2025 is the OECD series; MOSPI publishes official CPI-Combined
  inflation back to 2014, which should replace it.

## Repository layout

```
config/default.toml        all parameters and assumptions
src/inrfv/                 pipeline package (data, models, stats, backtest, report, run)
tests/                     unit, parser and no-look-ahead tests
data/raw/                  inputs + MANIFEST.sha256
data/processed/, outputs/*.png, notebooks/   legacy v0.1–0.2 artefacts (see notebooks/README.md)
outputs/runs/              pipeline runs (git-ignored)
```
