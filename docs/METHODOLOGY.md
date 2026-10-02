# Methodology

Full method notes for the USD/INR fair value model, grouped by topic. The [README](../README.md)
is the overview; [REVIEW.md](REVIEW.md) is the argument for outside reviewers. The version
in brackets after a heading is the release that introduced it ([CHANGELOG](../CHANGELOG.md)).

Sign convention: positive misalignment = INR undervalued (weaker than fair).
Every assumption is in [`config/default.toml`](../config/default.toml).

## Contents

- [1. Data and timing](#1-data-and-timing)
- [2. REER component](#2-reer-component)
- [3. FEER](#3-feer)
- [4. Composite, forecasts and uncertainty](#4-composite-forecasts-and-uncertainty)
- [5. Validation against outside benchmarks](#5-validation-against-outside-benchmarks)
- [6. Market, flows and regimes (diagnostics)](#6-market-flows-and-regimes-diagnostics)
- [7. Data sources](#7-data-sources)

## 1. Data and timing

Every reading uses only data public at that month-end; revisions are checked separately.

**Point-in-time data.** `panel_reference_month` holds values by the month they
refer to. `panel_point_in_time` holds what was public at each month-end, using
the publication lags in the config: USD/INR, DXY, Brent, VIX, rates and reserves 0;
REER, CPI and trade 1; monthly FPI/FDI 2; quarterly BoP 6 months after the quarter
start; annual World Bank data 7 months after year end. Revisions are not modelled.

**Data vintages (v0.8).** Point-in-time handling covers publication lags; this covers
revisions.

- *RBI revisions:* the DBIE Excel files and the RBIH Data API are two vintages of the
  same series. Every run re-runs the headline models on a dataset that prefers the
  earlier vintage wherever both exist (`[dbie] mode = "merge_early"`), and compares
  each point-in-time reading. Between the two vintages the RBI revised the BoP
  current account (up to 15%), FDI and loans (up to 35%), monthly FDI and imports.
  The headline moved in 30 of 267 months, by at most 0.48 points (June 2026, through
  the FEER; 0.17 before the v0.17 FEER changes). Revisions to RBI data matter little for the reading. This is a lower bound,
  since the earlier files are themselves partly revised.
- *Past vintages:* every refresh commits data/raw, so the git history is a dated
  archive of inputs. `python -m inrfv.vintages run <git-rev>` re-runs the full
  pipeline on data/raw as committed at that revision.
- *US CPI:* with a FRED API key, US inflation at each month-end comes from FRED's
  real-time archive (ALFRED), as published then, which also captures the actual
  release calendar. The vintages are cached in data/raw/alfred, and the report states
  how far they differ from the revised series. Without a key, the revised series with
  a one-month lag is used and the report says so.

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

## 2. REER component

The panel anchor is the REER component of the composite; the HP gap and the India-only anchor are reported alongside.

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

*Formal panel cointegration and the specification search (v0.15).* The check above
is a Fisher combination of ADF tests on the pooled, common-slope residuals. The formal
tests let each country have its own slope. They are Pedroni-type group and panel ADF
on country-by-country cointegrating regressions, and Westerlund's Gt and Pt
error-correction tests (`stats/panel_coint.py`). Their p-values come from 999
bootstrap panels generated under no cointegration, with years resampled jointly
across countries to keep cross-country correlation.

A Monte Carlo (`scripts/mc_panel_coint.py`) fixed the primary statistic. The group ADF
rejects 5% of non-cointegrated panels at 5%; the Westerlund bootstrap rejects 15–18%,
so its p-values are too low here. The search family is every combination of
productivity with government consumption, openness, terms of trade and NFA: 16
specifications, 12 with enough years.

| | Group ADF p | Holm | BH |
|---|---|---|---|
| Productivity only (central) | 0.023 | 0.25 | 0.09 |
| Specifications passing at 5%, before adjustment | 5 of 12 | 0 | 0 at 5%, 10 at 10% |

Each country's REER is broadly cointegrated with its own productivity. The central
result does not survive a family-wise correction for the search (Holm 0.25). It holds
at a 10% false-discovery rate (BH 0.09). So the anchor's equilibrium is suggestive,
not conclusive, which is now quantified. The p-values themselves vary by about ±0.01
between bootstrap seeds.

**REER component choice.** All three REER measures run every time;
`[composite] reer_component` picks one (`panel`, `hp` or `anchor`). Composite
backtests: panel anchor 12-month RMSE ratio 1.02, Clark-West p 0.22, α always
negative; HP gap 1.05, p 1.00, α changes sign; India-only anchor 1.37.

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

## 3. FEER

External sustainability, IMF EBA style: the current account against the IMF's norm, converted to a REER gap.

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

**FEER: cyclical adjustment and income term (v0.17).**

- *Cyclical adjustment.* As in the IMF's EBA, the current account is adjusted for
  India's output gap relative to its partners'. The EBA coefficient is −0.3564; the
  EBA terms-of-trade term is not added because the oil adjustment already covers it.
  India's gap uses a one-sided HP filter on log 4-quarter real GDP. All quarterly
  bases are linked onto the 2022-23 series, which runs to Apr–Jun 2026; the data are
  not seasonally adjusted, so the 4-quarter sum also matches the CA window. The
  partners' gap averages the US (against CBO potential) and the euro area (one-sided
  HP). Checked against the IMF: India's gap correlates 0.96 with the EBA's
  (2017–2023), and the cyclical contribution 0.84 (2017–2025).
- *Income term.* A real appreciation raises dollar GDP and shrinks the
  foreign-currency part of the net primary income deficit (−1.3% of GDP) relative to
  GDP. The term is −share × income/GDP / 100. The foreign-currency share is unknown:
  0.5 centrally, drawn uniformly on [0, 1] in the bands.

| Jan–Mar 2026 quarter | FEER misalignment |
|---|---|
| Before | +10.0% |
| + cyclical adjustment | +12.5% |
| + income term | +10.4% |
| Both (now) | +13.0% |

The composite backtest improves slightly (12-month ratio 0.977 to 0.964), and the
headline moves from +14.1% to +15.7%. The bootstrap corridor's ex-post coverage falls
from 75% to 66%. It is still closer to nominal than the end-to-end band (100%), and
its misses are still on the side of overstated undervaluation.

## 4. Composite, forecasts and uncertainty

How the two components are combined, tested out of sample, and given a range.

**Composite and ECM.** ECT = 0.5 × REER component gap + 0.5 × FEER gap (log). The backtest
regresses h-month INR changes on the ECT using only realised targets and compares
against a random walk with drift.

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

**Corridor recalibration (v1.1).** After the v0.17 FEER changes the bootstrap covered
only 66%, so the corridor is now recalibrated against its own misses (split-conformal).
Each month's ex-post miss is measured in units of that month's half-width on the side
it fell; k is the finite-sample 80th percentile of those scores. Two candidates: *scale*
(one factor k on both sides) and *shift and scale* (also moves the centre by the mean
past miss). The rule was set before computing them: judge on leave-one-year-out
coverage; keep the raw corridor unless a candidate is closer to 80%; prefer scale
unless shift and scale is closer by more than 5 pp.

| Corridor | Shift | k | One year out | Real time (Aug 2020 on) | Median width, real time |
|---|---|---|---|---|---|
| Raw bootstrap | 0 | 1 | 66% (33% below) | 77% | 9.0 pp |
| **Scale (adopted)** | 0 | 1.23 | **78%** (22% below) | 95% | 13.4 pp |
| Shift and scale | −2.5 pp | 0.91 | 69% (19% below, 11% above) | 63% (37% above) | 6.5 pp |

In real time a month uses only years whose IMF assessment had been published, and at
least three of them, so the recalibrated history starts in Aug 2020. The adopted
corridor over-covers in real time: the misses cluster in 2017–21, and since 2022 the
raw corridor has covered, so a correction learned from the early years is too wide
later, and a shift learned then over-corrects. Nine assessed years is a small
calibration set; k is re-fitted each July as the IMF publishes. The Sep 2026 corridor
moves from 78.70–85.08 to 77.90–85.77. The ex-post fair value still uses the final
panel coefficients, which were not known in real time.

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

## 5. Validation against outside benchmarks

**External benchmark: the IMF (v0.10).** Each year the IMF's External Balance
Assessment (EBA) assesses India's current account and real exchange rate for the
previous year. India's rows for the 2017–2025 analyses (ESR 2018–2026) were extracted
from the IMF's "EBA estimates" tables into `data/raw/manual/imf_eba_india.csv`
(`scripts/extract_imf_eba.py`). Every run compares them with this model, on the same
sign convention (positive = undervalued):

| This model vs IMF | Same sign | Mean abs. difference at IMF publication | Correlation at publication |
|---|---|---|---|
| Composite vs IMF CA model (CA gap / elasticity) | 9 of 9 years | 2.2 pp (ours 1.5 pp more undervalued) | 0.71 |
| FEER vs IMF CA model | 9 of 9 | 4.7 pp | 0.85 |
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

## 6. Market, flows and regimes (diagnostics)

These explain moves and pricing; they do not enter the fair value.

**BEER (v0.4).** Following Clark & MacDonald, the bilateral *real* USD/INR rate
(PPP imposed: log USD/INR minus log CPI India plus log CPI US) is regressed by
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
this asks what moved the spot rate. The monthly USD/INR % change is regressed on net
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

*Identifying the flow effect (v0.18).* The attribution's −0.13% per US$1 bn is a
same-month association, and flows and the rupee feed each other. With no free,
clean instrument (EM fund-flow data are proprietary), the effect is bounded instead
(`models/flow_id.py`, monthly 2011–2026):

| Method | Impact | After 2 / 4 / 6 months |
|---|---|---|
| Recursive, flows move the rupee within the month (A) | −0.130 (t −3.8) | −0.167 / −0.149 / −0.067 |
| Recursive, the rupee moves flows within the month (B) | 0 by construction | −0.018 / −0.010 / +0.082 (none significant) |
| 2SLS, instruments: changes in VIX and US 10-year yield | −0.070 (t −1.1) | |

Both recursive orderings condition on same-month global moves (VIX, US 10-year,
dollar) and two lags of everything; the horizons come from local projections. The IV
first stage is strong (F 21) and Hansen's J does not reject (p 0.16). Exclusion is
untestable, though: global risk shocks reaching the rupee only through portfolio
flows, given the dollar, is a strong assumption. So the same-month estimate is the
upper end of the identified range, and the IV puts the effect at about half of it.
The portfolio-flow contributions and the RBI's absorbed pressure in the attribution
are upper bounds; the report shows both.

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

**Regimes.** Two-state Markov switching in the mean and variance of monthly INR
returns, re-estimated every 12 months; filtered probabilities only. Oil × DXY
quadrants use expanding medians.

**Time-varying transition probabilities (v0.16).** Do oil, the VIX, portfolio flows or
RBI intervention change the odds of switching between calm and stress? Each driver is
lagged one month, point in time, and enters a logistic TVTP Markov-switching model
(`models/regimes_tvtp.py`). Each is compared with the constant-probability model. The
deciding test, set beforehand, is out of sample (2008–2026): the one-step-ahead
predictive log score of each month's return, with parameters re-estimated yearly.

| Transition drivers | AIC | BIC | Out-of-sample log score vs constant | p | AUC, big-move months |
|---|---|---|---|---|---|
| Constant (headline) | **1098.6** | **1121.1** | — | — | **0.66** |
| Brent | 1101.8 | 1131.9 | −0.004 | 0.70 | 0.64 |
| VIX | 1101.9 | 1132.0 | −0.015 | 0.94 | 0.64 |
| RBI intervention | 1100.5 | 1130.6 | −0.019 | 0.85 | 0.65 |
| FPI | 1099.3 | 1129.4 | −0.027 | 0.80 | 0.65 |
| All four | 1110.2 | 1162.8 | −0.525 | 0.99 | 0.58 |

No driver improves the next month's forecast over the regimes' own persistence, and
all four together overfit. The constant model stays. A simulation in the tests checks
that the same machinery does detect a driver that really moves the odds.

## 7. Data sources

| Source | Series | How |
|---|---|---|
| RBI DBIE via the RBIH Data API | USD/INR, REER/NEER (40-currency), reserves, trade, quarterly BoP, monthly FDI/portfolio flows, weighted average call rate | Automatic, cached in `data/raw/dbie/` |
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
| RBI (RBIH Data API) | Daily USD/INR reference rate, weekly FX reserves | Automatic; monthly averages fill gaps in, and extend, the monthly USD/INR series; weekly reserves fill gaps only |

**RBI data.** DBIE itself has no public API. The pipeline reads DBIE's series from
the [Reserve Bank Innovation Hub](https://github.com/Reserve-Bank-Innovation-Hub/dbie.rbihub.in)'s
public, read-only Data API (`https://data-api.dbie.rbihub.in`), a daily mirror of
DBIE's SDMX series run by an RBI subsidiary. It merges these with any DBIE Excel
files in `data/raw`. Where both sources have a value, the later release wins (RBI
revises recent months). Every run reports each series' coverage, which source was
newer, and any disagreement outside the normal revision window. Missing USD/INR
months, and months after RBI's latest, are filled with FRED's EXINUS rescaled to
RBI's level, and the report says so. `[dbie] mode` in the config switches between
`merge`, `api` and `xlsx`.

See [`data/raw/manual/README.md`](../data/raw/manual/README.md) for manual inputs.
