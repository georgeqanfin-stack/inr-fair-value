# INR/USD fair value: technical write-up for outside review

Version 1.1 · data as of September 2026 · run `20261002-001918` · repository
[georgeqanfin-stack/inr-fair-value](https://github.com/georgeqanfin-stack/inr-fair-value)

This document is for a reviewer who has not seen the project. It states what the model
claims and how each claim is tested. It also lists every choice made after seeing a
result, and what we would most like checked. The [README](../README.md) is the full
reference; this is the argument. All figures come from
`reports/latest/results.json` unless marked otherwise.

---

## 0. What we ask of a reviewer

1. **Replicate the headline** (section 10). One Docker command reproduces the
   September 2026 reading from committed data, with no network access and no API key.
2. **Attack the design.** Section 9 lists the questions we are least sure of. The ones
   that matter most are look-ahead leaks (Q1), the ex-post benchmark used to calibrate
   the range (Q4), and whether the specification search is fully disclosed (Q6).
3. **Report by issue** on the repository, or in any form. Every number here traces to
   a function in the map in section 11.

---

## 1. Summary

**Claim.** In September 2026, at a spot rate of 95.41 per dollar, the rupee is about
**16% undervalued** against a composite fair value of **82.50**. The 80% range is
**77.90–85.77**, recalibrated so that it would have covered the later re-estimate
about 78% of the time. The spot rate is above the whole range, and all 2,000 joint
simulation draws say undervalued.

**What we do not claim.**
- **No timing signal.** The composite gap does not forecast the rupee significantly
  better than a random walk with drift. At 12 months the RMSE ratio is 0.964 and the
  Clark-West p is 0.12.
- **The long-run anchor is not established.** The REER component's equilibrium rests
  on a panel cointegration result that does not survive a correction for the
  specifications searched (Holm p 0.25).
- **The flow effect is bounded, not point-identified.**

**Why the reading is still informative.** It has the same sign as the IMF's current
account model in all 9 assessed years (2017–2025). Its peer ranking orders 19 emerging
market currencies much as the IMF's REER model does (mean rank correlation 0.83). It
moves the expected way in 6 of 7 currency crises fixed in advance. And every number
uses only data public at the date it refers to.

---

## 2. Question and conventions

- **Target:** the medium-term equilibrium of the rupee, expressed as a fair INR/USD
  rate. Misalignment is measured on the real effective rate. It is converted to
  INR/USD by holding the dollar's share constant: fair = spot × exp(−gap).
- **Sign:** positive misalignment = rupee **weaker** than fair (undervalued).
- **Frequency:** monthly readings, January 2000 onward. Each reading uses only data
  published by that month-end.
- **Configuration:** every assumption is in `config/default.toml`, and every run
  records the config hash, the code revision and SHA-256 hashes of every input.

---

## 3. Data and point-in-time design

| Source | Series | Publication lag applied |
|---|---|---|
| RBI via the RBIH Data API (a public mirror of the RBI's DBIE database) | INR/USD (daily reference rate, monthly mean), 40-currency REER/NEER, reserves, BoP (BPM6), IIP, FPI/FDI, intervention (Bulletin Table 4), forward premia, real GDP | Market data 0; REER 1 month; monthly flows and intervention 2 months; quarterly BoP 6 months after quarter start |
| MOSPI via RBI Bulletin | CPI-Combined (2024 = 100; earlier bases linked) | 1 month |
| FRED / ALFRED | US CPI (real-time vintages), Fed funds, DXY, Brent, VIX, US 10-year, BIS broad REERs for 19 EMs, US/euro-area GDP and potential | Real-time vintages where available, otherwise 1 month |
| World Bank WDI | GDP per capita (PPP), government consumption, openness, terms of trade (19 EMs) | 7 months after year end (terms of trade 18) |
| Lane & Milesi-Ferretti, External Wealth of Nations | Net foreign assets (diagnostic only) | 16 months |
| IMF EBA estimate tables (ESR 2018–2026), Article IV reports | India's current account norm, cyclically adjusted CA, elasticity; 11 peers' REER gaps | From each table's publication month |

**Point-in-time construction.** Two panels are built. `panel_reference_month` holds
values by the month they refer to. `panel_point_in_time` holds what was public at each
month-end. Every model is re-estimated on an expanding window using only the second.
Where a model needs annual data, the data enter from their publication date, not the
year they describe. `tests/test_no_lookahead.py` checks this directly. For example, it changes prices after a
forecast date and asserts that the forecast does not move, and it checks that training targets
are fully realised.

**Revisions.** Publication lags handle timing; three mechanisms handle revisions:
- *RBI revisions:* the older DBIE Excel files and the API are two vintages of the
  same series. Every run re-computes the headline on the earlier vintage. The headline
  differs in 30 of 267 months, by 0.01 pp on average and at most 0.48 pp (June 2026).
- *US CPI* comes from ALFRED real-time vintages.
- *Archive:* every monthly refresh commits `data/raw`, so the git history becomes a
  dated archive of inputs. `python -m inrfv.vintages run <rev>` replays any of them.

India's CPI, trade and national accounts before this archive starts are **not** real
time; only their publication lags are modelled.

---

## 4. Models

The composite averages two independent routes to equilibrium. Everything else in the
repository is a diagnostic or a cross-check.

### 4.1 REER component: panel anchor (19 emerging markets)

India's own 25 years cannot pin down a REER equilibrium, so, as in the IMF's EBA REER
model, the coefficients come from a panel. The specification is panel dynamic OLS of
the log annual BIS broad REER on relative productivity (GDP per capita at PPP relative
to the world). It has country fixed effects and standard errors clustered by country.
The panel is 19 EMs from 1996 to 2024 and is re-estimated whenever a new World Bank
year is published.

India's equilibrium is its country effect plus the pooled slope times its latest
fundamentals. The productivity coefficient is +0.31 (t 4.4).

Because the country effect is India's mean residual, the anchor measures deviation from
India's own fundamentals-adjusted average. It is not an absolute level. That is also
why the peer comparison (section 5.3) uses rankings rather than levels.

### 4.2 FEER: external sustainability, IMF-style

For each BoP quarter, using data public at its release:
- **Underlying CA:** the trailing four-quarter current account as % of GDP, with three
  adjustments:
  - *oil:* net oil imports × (1 − Brent norm / Brent paid), with the norm a trailing
    5-year mean;
  - *cycle:* the EBA coefficient −0.3564 times India's output gap minus its partners'.
    India's gap uses a one-sided HP filter on 4-quarter real GDP; the partners are the
    US (CBO potential) and the euro area. India's gap correlates 0.96 with the EBA's
    over 2017–23.
  - *measurement error:* drawn in the bands only.
- **Norm:** the IMF's published norm for India, each applying from its publication
  month (−3.4% in 2013 to −2.3% in 2026). Before Feb 2013 the earliest norm is
  backcast.
- **Semi-elasticity:** the EBA formula −(η_x·X/GDP + η_m·M/GDP)/100, with η_x 0.46 and
  η_m 0.25 and India's gross trade shares. It also includes an income term for the
  foreign-currency share of net primary income (0.5 centrally, uniform on [0, 1] in
  the bands). The result is about −0.16 pp of GDP per 1% REER, which falls inside the
  IMF's own 0.15–0.18 for India.
- **Gap:** log(1 − (underlying CA − norm) / semi-elasticity / 100). For Jan–Mar 2026 it
  is +13.0%.

### 4.3 Composite and error-correction test

The composite misalignment is the equal-weighted average of the two log gaps. The
error-correction test regresses the h-month change in log INR/USD on the lagged
composite gap. It is re-estimated each month on an expanding window, training only on
fully realised targets.

### 4.4 Joint uncertainty range

Each month, 2,000 joint draws combine:
- the panel slope and India's effect (a country-block bootstrap, 300 draws per
  re-estimation);
- the IMF norm (its published standard error);
- both trade elasticities (±50%) and the income share;
- CA measurement error (sd 0.2 pp of GDP);
- the combination weights (equal, performance or inverse variance).

The raw range is the 10th–90th percentile. It is then recalibrated against its own
past misses (section 5.4).

### 4.5 Reported but not in the composite

| Model | Why it is outside the composite |
|---|---|
| One-sided HP REER gap | Cyclical by construction; composite built on it has α changing sign, CW p 1.00 |
| India-only REER fundamentals anchor | Not cointegrated (Engle-Granger p 0.85, 12 variants 0.60–0.87); forecasts worse (ratio 1.37) |
| BEER (real INR/USD on dollar, productivity, rates) | Not cointegrated (p 0.78–0.99) |
| Markov-switching regimes | Regime-conditional α does not differ; time-varying transition drivers do not help (section 7) |
| Flow attribution, RBI intervention, forward premia | Explain past moves or market pricing ex post; they do not define equilibrium |

---

## 5. Validation

### 5.1 Out-of-sample forecasts (Jun 2010 – Sep 2025)

| Horizon | n | RMSE ratio vs drift | OOS R² | Clark-West p (one-sided) | Hodrick t (in sample) |
|---|---|---|---|---|---|
| 1 month | 206 | 0.996 | 0.009 | 0.11 | −2.39 |
| 3 months | 202 | 1.000 | 0.000 | 0.22 | −2.07 |
| 6 months | 196 | 0.998 | 0.004 | 0.17 | −2.19 |
| 12 months | 184 | 0.964 | 0.070 | 0.12 | −2.05 |

The 12-month α is negative in every out-of-sample window (−0.70 to −0.25), so the gap
always has the error-correcting sign. The 12-month hit rate (83%) equals that of a
naive "the rupee depreciates" rule, so it is not evidence of skill. **Conclusion:** the
gap is economically sensible and correctly signed, but its forecasting gain is not
statistically significant. This is typical for exchange rates.

### 5.2 The IMF's own assessments (India, 2017–2025)

Both sides are on the same sign convention. "At publication" compares this model's
reading in the month each IMF table was published.

| This model vs IMF | Same sign | Mean abs. difference | Correlation |
|---|---|---|---|
| Composite vs IMF CA model (CA gap / elasticity) | 9 of 9 | 2.2 pp (ours 1.5 pp more undervalued) | 0.71 |
| FEER vs IMF CA model | 9 of 9 | 4.7 pp | 0.85 |
| REER component vs IMF REER-level model | 1 of 9 | 11.6 pp | 0.79 |

The FEER-vs-CA pairing is **not independent**: the FEER uses the IMF's norms, though
with its own CA data, oil and cyclical adjustments, and elasticity. The REER component
tracks the IMF's REER models' movements but sits about 12 points more undervalued. The
IMF's two approaches themselves disagree on India's sign in most years.

### 5.3 Peers and crises

- **Ranking:** the panel gives all 19 currencies a monthly point-in-time gap. In
  September 2026 India ranks 3rd most undervalued of 19.
- **Against the IMF's REER-index model** (11 overlapping currencies, 2017–2025):
  pooled correlation 0.80; mean within-year rank correlation 0.83, never below 0.74;
  within-country correlation 0.86. Against the IMF's CA model the correlation is
  −0.20, but the IMF's own REER models do not match its CA model across countries
  either.
- **Crisis episodes,** listed in the config before results were seen: 6 of 7 move the
  expected way. They are Turkey 2018, Brazil 2015, South Africa 2015, Mexico 2016,
  Mexico 2023–24 (towards overvaluation) and India 2013. China's August 2015
  devaluation fails: the renminbi's trade-weighted rate barely fell.

### 5.4 Does the range cover the truth?

A range is honest if the fair value, re-estimated later with better information, falls
inside it about 80% of the time. For each month of 2017–2025, an ex-post value is built
from:
- the panel coefficients as finally estimated;
- the IMF's own norm for that year, published the year after;
- the current account of that quarter.

The range is then recalibrated split-conformally. Each month's miss is measured in
units of that month's half-width on the side it fell, and the widening factor k is the
finite-sample 80th percentile. The rule was fixed in the config before computing.

| Range | One year left out | Real time (Aug 2020 on) | Median width |
|---|---|---|---|
| End to end (old) | 100% | — | 18.9 pp |
| Raw joint bootstrap | 66% (33% of months below) | 77% | 9.0 pp |
| **Scaled, k = 1.23 (adopted)** | **78%** | 95% | 13.4 pp |
| Shifted −2.5 pp and scaled 0.91 | 69% | 63% | 6.5 pp |

The misses cluster in 2017–21, when the real-time reading overstated undervaluation.
Since 2022 the raw range has covered. So the miscalibration is **not stable over time**:
the adopted correction is too wide in real time. Nine assessed years is a small
calibration set.

---

## 6. Ledger of choices

Each row is a decision that could have been made differently. "Before" means the rule
was written down before the competing results were computed.

| Choice | Alternatives tried | Decided | Note |
|---|---|---|---|
| REER component = panel anchor | HP gap, India-only anchor | Before the v0.4 backtest, on cointegration grounds; backtest agreed | |
| Panel spec = productivity only | 16 combinations with government consumption, openness, terms of trade, NFA | **After**: the only spec passing the Fisher check | Formal family-wise p: Holm 0.25, BH 0.09 (v0.15) |
| Group ADF as primary panel statistic | Westerlund Gt/Pt, panel ADF | By Monte Carlo size before reading India's p | Westerlund over-rejects (15–18% at 5%) |
| IMF norm path as central norm | Fixed −2.0, NIIP-stabilising, legacy −2.5, panel-estimated norm | Before | NIIP-stabilising norm reads +0.9% vs +13.0% |
| Equal composite weights | Performance, inverse variance, each alone | Before (rule in config) | Performance 0.963 vs equal 0.964 |
| Linear ECM | Threshold, ESTAR, rolling, Kalman TVP | Rule before; **robustness requirement added after** the rolling window passed | Rolling 0.944 at 120 months, median gain 0.007 across 72–180 |
| Constant regime transitions | Brent, VIX, FPI, intervention, all four | Before | None improve the predictive log score |
| Bootstrap range as headline | End-to-end band | **After** the coverage test | Disclosed in the README and report |
| Scale recalibration | Shift and scale, raw | Before (rule in config) | Real-time over-coverage reported |
| FEER cyclical adjustment and income term | Without either | Before (IMF method) | Raised FEER from +10.0% to +13.0% and the composite from +14.1% to +15.7% |
| Crisis episode list | — | Before | |

---

## 7. Negative results

These are kept in the pipeline and reported every run:
- **India-only fundamentals and the BEER:** none of their specifications is
  cointegrated.
- **NFA:** the wrong sign in the panel, and it breaks the panel test (p 0.42).
- **A panel-estimated CA norm:** R² 0.09, dropped.
- **Nonlinear and time-varying ECMs:** forecast worse (12-month ratios 1.30–1.42).
- **Time-varying transition probabilities:** no gain; all four drivers together
  overfit.
- **Rates in the BEER:** neither the forward premium nor the policy-rate gap adds
  anything (t −0.5).
- **UIP:** the slope is 0.60 (se 0.44), uninformative.
- **The forward premium's spread over the policy gap:** at its 86th percentile, but
  it does not predict next month's move.
- **Intervention as a regressor:** no effect (t 0.2), as expected from reverse
  causality, so it is modelled as a reaction function instead.

---

## 8. Limitations and threats to validity

1. **Forecast power.** Not statistically significant at any horizon.
2. **The anchor's statistical basis.** It is suggestive after the multiplicity
   correction, and the World Bank fundamentals lag one to two years, so the
   equilibrium moves in annual steps.
3. **The norm.** The reading is sensitive to the CA norm: the IMF and
   NIIP-stabilising norms differ by about 1.6 pp of GDP, which is worth 10–12
   points of misalignment (FEER +13.0% vs +0.9%). That is wider than the range. Before 2013 the norm is
   backcast, and the FEER's 2002–08 readings (+25 to +55%) mostly reflect that.
4. **Ex-post benchmark.** The coverage test uses final panel coefficients and the
   IMF's norms. Both are model outputs, not observed truths.
5. **Real-time India data.** Only publication lags are modelled before the vintage
   archive begins (October 2026); RBI revision effects are a lower bound.
6. **Flows.** The portfolio-flow effect lies between 0 and −0.13% per US$1 bn (IV
   −0.07, first-stage F 21, Hansen J p 0.16). Exclusion of the instruments (VIX, US
   10-year) is untestable. Attribution shares are upper bounds; the RBI's absorbed
   pressure is a lower bound.
7. **Single maintainer, no independent replication yet.** That is the purpose of
   this document.

---

## 9. Questions for reviewers

1. **Look-ahead.** Is any input used before its publication date? The riskiest places:
   - the BPM6 BoP merge (latest quarters only);
   - the GDP base splicing (`data/dbie.py: fetch_real_gdp`);
   - the output-gap filters, which are one-sided, but the partners' potential (CBO) is
     itself revised;
   - the timing of the IMF norm file.
2. **Panel anchor.** Is a country-fixed-effect DOLS on annual BIS REERs a sound basis
   for India's equilibrium? Would you weight the 0.023 or the Holm 0.25?
3. **Composite.** Is an equal average of a relative-to-history REER gap and an absolute
   FEER gap coherent, given that they measure different things?
4. **Coverage benchmark.** Is "final panel fit + IMF's later norm" a fair stand-in for
   the truth? Is there a better ex-post target?
5. **Conformal step.** With about nine effective observations, is scaling sound, or
   should the range simply be reported raw with its coverage?
6. **Search.** Is anything missing from the ledger in section 6?
7. **Flows.** Would a free proxy for EM fund flows identify the effect better than VIX
   and US yields?
8. **Communication.** Do the note and dashboard overstate the confidence implied by
   sections 5 and 8?

---

## 10. Replication

From a clean clone, with no network and no key (uses committed `data/raw`):

```bash
docker build -t inrfv .
docker run --rm inrfv python -m inrfv.run
```

Or natively (Python 3.12):

```bash
pip install -r requirements.txt && pip install -e .
python -m inrfv.run
```

**Expected:** `Composite fair 82.50 misalignment +15.7% (Sep 2026)` and
`12m OOS: RMSE ratio vs drift 0.964, Clark-West p 0.121`.
- The full report is in `outputs/runs/<id>/report.md`, and every statistic is in
  `results.json`.
- Bootstrap results are seeded, so they reproduce exactly. A fresh clone, run offline
  with no API key, reproduced every headline figure to the last digit (2 Oct 2026),
  including the range 77.90–85.77.
- A first run takes about 9 minutes, because the cached diagnostics (panel
  cointegration with 999 draws; TVTP regimes) are recomputed when `outputs/cache/` is
  absent. Later runs take about 2–3 minutes.

**Checks:**
- `python -m pytest` runs 164 tests, including no-look-ahead tests, simulation
  recovery tests and an end-to-end run.
- `data/raw/MANIFEST.sha256` verifies the inputs, and each run reports any mismatch.
  Text files are hashed with line endings normalised, so a Windows or Linux checkout
  verifies the same way.
- `python -m inrfv.refresh` re-downloads everything (`FRED_API_KEY` in `.env` for
  ALFRED; the RBIH Data API needs no key).

**Manual inputs** (`data/raw/manual/`) are the IMF norms and EBA tables, with sources
row by row in `data/raw/manual/README.md`. The EBA PDFs themselves are not committed;
`scripts/extract_imf_eba.py` rebuilds the CSVs from them.

---

## 11. Map from claims to code

| Claim | Code | Test |
|---|---|---|
| Point-in-time panel | `src/inrfv/data/build.py` (`build_pit`) | `test_no_lookahead.py`, `test_data_build.py` |
| Panel anchor, peers | `models/panel_anchor.py`, `models/peers.py` | `test_panel_anchor.py`, `test_peers.py` |
| Formal panel cointegration | `stats/panel_coint.py`, `scripts/mc_panel_coint.py` | `test_panel_coint.py` |
| FEER, cyclical adjustment | `models/feer.py`, `data/build.py` (`output_gaps`) | `test_feer_cyclical.py`, `test_no_lookahead.py` |
| Composite, ECM backtest | `models/composite.py`, `backtest.py` | `test_no_lookahead.py`, `test_signs_and_regimes.py`, `test_end_to_end.py` |
| Weights | `models/weights.py` | `test_weights.py` |
| Range and recalibration | `models/uncertainty.py` | `test_uncertainty.py` |
| IMF benchmark | `models/benchmark.py` | `test_benchmark.py` |
| Revisions, vintages | `vintages.py`, `data/alfred.py` | `test_vintages.py` |
| Flow attribution, intervention | `models/flows.py` | `test_flows.py` |
| Nonlinear ECMs, breaks | `models/nonlinear.py` | `test_nonlinear.py` |
| Regimes (TVTP) | `models/regimes_tvtp.py` | `test_regimes_tvtp.py` |
| Flow identification | `models/flow_id.py` | `test_flow_id.py` |

## References

- Clark, P. and MacDonald, R. (1998), "Exchange rates and economic fundamentals: a
  methodological comparison of BEERs and FEERs", IMF WP/98/67.
- Clark, T. and West, K. (2007), "Approximately normal tests for equal predictive
  accuracy in nested models", *Journal of Econometrics*.
- Hodrick, R. (1992), "Dividend yields and expected stock returns", *Review of
  Financial Studies*.
- IMF (2018–2026), *External Sector Report*, and the External Balance Assessment
  methodology (Cubeddu et al. 2019, IMF WP/19/65).
- Lane, P. and Milesi-Ferretti, G. M., External Wealth of Nations database.
- Pedroni, P. (2004), "Panel cointegration", *Econometric Theory*; Westerlund, J.
  (2007), "Testing for error correction in panel data", *Oxford Bulletin of Economics
  and Statistics*.
- Vovk, V., Gammerman, A. and Shafer, G. (2005), *Algorithmic Learning in a Random
  World* (conformal prediction).
