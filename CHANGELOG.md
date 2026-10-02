# Changelog

Newest first. Method details for each release are in [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

| Version | Added |
|---|---|
| 1.2 | Live monitor on GitHub Pages, rebuilt after each monthly refresh; the monthly note and a what-if panel (norm, current account, elasticities, income share, weights) inside the dashboard; quoted as USD/INR throughout |
| 1.1 | Corridor recalibrated (conformal, against its own ex-post misses): one-year-out coverage 66% → 78% |
| 1.0 | Engineering: ruff, mypy, coverage gate (85%), data schemas as a refresh gate, Docker image built and tested in CI. Roadmap complete |
| 0.18 | Flow effect identified: recursive orderings, local projections, 2SLS with global push instruments |
| 0.17 | FEER: IMF-style cyclical adjustment (output gaps) and income term; quarterly real GDP to Apr–Jun 2026 |
| 0.16 | Regime model with time-varying transition probabilities tested; constant kept |
| 0.15 | Formal panel cointegration (Pedroni-type, Westerlund) with bootstrap p; 16-spec family, Holm/BH |
| 0.14 | Nonlinear/time-varying ECM variants and break tests; linear ECM kept (rolling not robust) |
| 0.13 | Joint bootstrap corridor (panel, norm, elasticities, CA error, weights) with ex-post coverage check |
| 0.12 | Composite weights tested: equal vs performance vs inverse-variance; equal kept by a pre-set rule |
| 0.11 | Peer currencies: gaps for all 19, India's rank, crisis episodes, cross-section vs the IMF |
| 0.10 | IMF track record: EBA assessments 2017–2025 vs this model; ALFRED US CPI live |
| 0.9 | Automatic inputs: CPI 2024=100 and BPM6 BoP from RBI Bulletin tables, USD/INR from RBI daily rates, reserves gaps from weekly data; 2026 IMF norm; smarter gates |
| 0.8 | Data vintages: revision check on every run, past-vintage runner, ALFRED US CPI (with a FRED key) |
| 0.7 | Forward premia: implied forwards, UIP test, spread over the policy gap, forward-based BEER |
| 0.6 | RBI FX intervention and forward book; [roadmap to 9/10](ROADMAP.md) |
| 0.5 | Monthly refresh with quality gates, dashboard, monthly note, NFA test, flow attribution |
| 0.4 | RBIH Data API, IMF-style FEER with the IMF norm path, panel REER anchor (19 EMs), official MOSPI CPI, BEER rework |
| 0.3 | Notebooks replaced by a tested, reproducible pipeline in which every number uses only data published at that date; see below |

## What changed in 0.3 (look-ahead removed)

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
