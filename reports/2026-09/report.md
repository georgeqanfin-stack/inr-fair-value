# INR/USD fair value: run report

inrfv 0.9.0 · run `20261001-144529` · as of **Sep 2026** (latest month with RBI INR/USD) · spot **95.41**

All figures are point-in-time: each value uses only data published by that month-end. Positive misalignment = INR undervalued (weaker than fair).

## Current reading

| Model | As of | Misalignment | Fair INR/USD | Notes |
|---|---|---|---|---|
| REER gap (one-sided HP) | Sep 2026 | +4.8% | 91.06 | cyclical gauge; mean-reverting by construction |
| REER panel anchor (EM panel) | Sep 2026 | +18.4% | 80.57 | productivity-based; BIS REER; spec 'prod' |
| REER fundamentals anchor | Sep 2026 | +10.1% | 86.62 | **not cointegrated**: reported only |
| FEER, IMF norm path (central) | Sep 2026 | +10.0% | 86.71 | BoP Jan–Mar 2026; 10–90th pct +5.2% to +16.8% |
| FEER, fixed IMF −2.0% norm | Sep 2026 | +8.2% | n/a | for comparison |
| FEER, NIIP-stabilising norm | Sep 2026 | -1.6% | n/a | alternative norm |
| FEER, legacy −2.5% norm | Sep 2026 | +11.3% | n/a | v0.2 assumption, for comparison |
| FEER conditional (experimental) | Jun 2026 | -1.5% | n/a | ad hoc norm, not in composite |
| BEER, current (real INR/USD, DOLS) | Sep 2026 | +25.2% | 76.23 | **not cointegrated**: descriptive only |
| BEER, total (permanent fundamentals) | Sep 2026 | +21.5% | 78.54 | fundamentals at one-sided HP trend |
| Composite (REER+FEER) | Sep 2026 | +14.1% | 83.59 | drives the ECM |

**Fair-value corridor (10th–90th percentile of FEER norm and elasticity uncertainty): 78.27 – 88.53** (central 83.59, spot 95.41).

### FEER, latest quarter

Quarter from Jan 2026, public Jul 2026: 4-quarter CA -0.68% of GDP; oil adjustment +nanpp (net oil imports n/a% of GDP, Brent paid $70 vs 5-year norm $82); underlying CA -0.68%. Norms: IMF path -2.3% (IMF 2026 External Sector Report (30 Jul 2026) Table 2.11 India: EBA norm -2.3 percent of GDP with standard error 0.6 [FY2025/26]), fixed IMF -2.0%, NIIP-stabilising -0.43%, legacy -2.5%. Semi-elasticity -0.161 pp/1% (EBA shares; X 21.6%, M 24.7% of GDP).

### REER panel anchor

REER component used in the composite: **panel**. Panel dynamic OLS with country fixed effects, annual BIS broad REER, 19 emerging markets, standard errors clustered by country; India's equilibrium = its country effect + pooled coefficients x its latest fundamentals.

| Spec | Years | n | Coefficients (t) | Panel coint. p | Countries rejecting | India p | India gap (last full year) |
|---|---|---|---|---|---|---|---|
| prod (central) | 1996–2024 | 551 | rel_prod +0.309 (+4.4, exp. +) | 0.025 | 21% | 0.08 | +8.8% (2025) |
| long | 1996–2024 | 549 | rel_prod +0.294 (+4.0, exp. +), gov_cons +0.004 (+0.5, exp. +), openness +0.001 (+0.5, exp. -) | 0.976 | 0% | 0.31 | +8.6% (2025) |
| short | 2007–2023 | 323 | rel_prod +0.147 (+0.7, exp. +), log_tot +0.166 (+0.9, exp. +), gov_cons -0.000 (-0.0, exp. +), openness -0.004 (-1.7, exp. -) | 0.999 | 5% | 0.45 | +2.6% (2025) |
| prod_nfa | 1996–2023 | 532 | rel_prod +0.318 (+4.4, exp. +), nfa -0.001 (-0.5, exp. +) | 0.415 | 11% | 0.39 | +10.0% (2025) |

Coefficient range across 23 point-in-time re-estimations since 2004-07: rel_prod +0.31 to +0.87. Twelve specifications were compared when this model was built; only productivity-only DOLS passed the panel check, so treat the cointegration result as suggestive. Net foreign assets (External Wealth of Nations) were tested later and are shown as `prod_nfa`: insignificant, wrong sign, and adding them breaks the panel check.

### BEER (bilateral, real INR/USD)

Real INR/USD with PPP imposed, regressed by dynamic OLS on long-run fundamentals; expanding window, first estimate 2009-01. Current BEER uses today's fundamentals; total BEER uses their one-sided HP trends.

| Spec | Sample | n | Coefficients (t, expected sign) | Engle-Granger p | Johansen rank |
|---|---|---|---|---|---|
| core (central) | 2001-02–2026-09 | 301 | log_dxy +0.723 (+8.6, +), rel_prod -0.409 (-8.3, -), real_rate_diff -0.002 (-0.5, -) | 0.975 | 0 |
| dxy | 2000-02–2026-09 | 314 | log_dxy +0.438 (+2.4, +) | 0.772 | 0 |
| oil | 2001-02–2026-09 | 301 | log_dxy +1.061 (+7.3, +), rel_prod -0.552 (-9.7, -), real_rate_diff -0.001 (-0.3, -), log_brent +0.119 (+3.4, +) | 0.983 | 0 |
| fwd | 2001-02–2026-08 | 300 | log_dxy +0.733 (+8.7, +), rel_prod -0.412 (-8.4, -), real_fwd_diff -0.002 (-0.5, -) | 0.982 | 1 |

Coefficient range across re-estimations: log_dxy +0.28 to +0.72, rel_prod -0.83 to -0.42, real_rate_diff -0.00 to +0.01.

Does the BEER gap predict INR/USD? (same out-of-sample test as the composite)

| h | OOS window | n | RMSE ratio vs drift | Clark-West p | α range |
|---|---|---|---|---|---|
| 1 | 2014-01–2026-08 | 152 | 1.006 | 0.626 | -0.03 to +0.00 |
| 3 | 2014-03–2026-06 | 148 | 1.053 | 0.549 | -0.17 to -0.03 |
| 6 | 2014-06–2026-03 | 142 | 1.074 | 0.452 | -0.27 to -0.07 |
| 12 | 2014-12–2025-09 | 130 | 1.086 | 0.127 | -0.55 to -0.27 |

Reading: the dollar and productivity coefficients are large, significant and correctly signed, but the real rate is not cointegrated with them, so the BEER gap describes where fundamentals would put the rupee, not a level it reliably returns to.

### REER fundamentals anchor (India only)

Dynamic OLS, 2005-07–2026-04, n=82: log REER on relative productivity +0.150 (t +2.4, expected +), log terms of trade +0.101 (t +0.8, expected +), NFA/GDP -0.241 (t -0.8, expected +). Engle-Granger p = 0.85 (5% critical -4.23). Range of each coefficient across the quarterly re-estimations since 2013-07: rel_prod +0.01 to +1.51, log_tot -0.04 to +0.68, nfa_gdp -0.24 to +2.18. NFA source quarters: {'BPM5': 49, 'BPM6': 29, 'cumulated CA': 2, 'not yet published': 2, 'interpolated': 1}.

Reading: India's productivity relative to the world has more than doubled since 2005 while the REER stayed within a narrow range, so the fundamentals do not pin down the REER level over this sample (consistent with a managed exchange rate). The anchor's misalignment is therefore not used in the composite unless `[composite] reer_component = "anchor"`.

Cross-check, FY2024/25: this model's CA -0.58% and underlying CA -0.50% vs the IMF's -0.6% actual and -0.4% cyclically adjusted (2025 Article IV); misalignment +9.6% (IMF: external position "moderately stronger" than fundamentals).

## Regime

Filtered P(stress) = **0.08** (2026-09), steady state 0.34. Forward: 1m 0.18, 3m 0.28, 6m 0.33, 12m 0.34.
Calm: mean +0.10%/mo, sd 0.76%, duration 7.8m. Stress: mean +0.49%/mo, sd 2.40%, duration 4.1m.

Oil × DXY quadrant (expanding medians): OilHi_DXYHi (Sep 2026).

## Market pricing (forward premia)

RBI inter-bank forward premia, monthly average (% a year), Jun 2026: 3-month 3.10%, 6-month 2.98%. Implied forwards on the Sep 2026 spot 95.41: 3-month 96.15, 6-month 96.83.

Premium over the policy-rate gap (3-month premium − (India policy rate − Fed funds)): +1.23 pp in Jun 2026, above 86% of months since 2000 (mean -0.37, sd 1.64). A high spread means dollars for future delivery cost more than the rate gap justifies: hedging demand and expected depreciation beyond carry.

Does the spread predict next month's rupee move? Coefficient -0.048% per pp (t -0.6); controlling for next month's dollar move -0.073 (t -1.2).

| UIP test | Sample | n | Slope (UIP = 1) | t vs 0 | t vs 1 | R² |
|---|---|---|---|---|---|---|
| 3m premium → 3-month depreciation | 2000-01–2026-06 | 318 | 0.60 (se 0.44) | +1.3 | -0.9 | 0.012 |
| 6m premium → 6-month depreciation | 2000-01–2026-03 | 315 | 0.59 (se 0.46) | +1.3 | -0.9 | 0.018 |

## Flow attribution (what moved the spot rate)

Monthly INR/USD % change regressed on net FPI and FDI flows (US$ bn), dollar-index and Brent % changes, 2011-03 to 2026-06 (n = 184, R² 0.34, Newey-West t). Ex post, by reference month; it explains spot moves and does not enter the fair value. Positive = rupee weaker.

| Term | Coefficient | t | Meaning |
|---|---|---|---|
| const | +0.530 | +3.7 | average monthly depreciation (drift) |
| fpi | -0.131 | -4.3 | % per US$1bn of net FPI inflow |
| fdi | -0.043 | -1.1 | % per US$1bn of net FDI inflow |
| dxy | +0.456 | +4.5 | % per 1% dollar-index rise |
| brent | -0.003 | -0.4 | % per 1% Brent rise |

| Window | Actual | Portfolio flows (FPI) | Direct investment (FDI) | Dollar index | Oil (Brent) | Drift | Residual | FPI, fitted without the window |
|---|---|---|---|---|---|---|---|---|
| Apr 2026–Jun 2026 | +2.4% | +1.3 | -0.3 | +0.1 | +0.1 | +1.6 | -0.3 | +1.2 |
| Jul 2025–Jun 2026 | +10.0% | +3.8 | -0.3 | -0.2 | -0.1 | +6.4 | +0.4 | +3.7 |

Direction: FPI this month → INR next month t -2.6 (p 0.009); INR last month → FPI this month t -2.0 (p 0.050). Reading: one-way or none at the 5% level. Flow data end Jun 2026.

### RBI intervention

RBI Bulletin Table 4: spot net purchases plus the change in the outstanding forward book (US$ bn; negative = net dollar sales). Intervention is not a regressor: the RBI sells because the rupee is under pressure, and a direct regression finds +0.002% per US$1bn (t +0.2). Reaction function: the RBI buys +1.20 bn per US$1bn of net FPI inflow (t +4.8) and -0.72 bn per 1% rupee depreciation (t -1.7); R² 0.31.

Absorbed pressure values each dollar the RBI sold at the market price implied by the FPI coefficient (0.131% per US$1bn). That coefficient is net of the RBI's usual response, so the absorbed share is a lower bound; it scales linearly with the price.

| Window | RBI net sales | Actual move | Held stronger by | Move without RBI | Share absorbed |
|---|---|---|---|---|---|
| Apr 2026–Jun 2026 | US$14.7 bn | +2.4% | +1.9 pts | +4.3% | 45% |
| Jul 2025–Jun 2026 | US$107.0 bn | +10.0% | +14.0 pts | +24.0% | 58% |

Outstanding net forward position, Jul 2026: US$-136.8 bn (-20% of FX reserves). Latest month of intervention data: Jul 2026 (US$-14.8 bn).

## Out-of-sample backtest (ECM vs random walk with drift)

| h | OOS window | n | RMSE ratio | OOS R² | Clark-West p | DM p | hit ECM | hit naive 'depreciate' | hit vs drift | α range |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2009-07–2026-08 | 206 | 0.998 | +0.003 | 0.145 | 0.853 | 58% | 58% | 49% | -0.06 to -0.01 |
| 3 | 2009-09–2026-06 | 202 | 1.006 | -0.011 | 0.280 | 0.771 | 60% | 63% | 42% | -0.20 to -0.03 |
| 6 | 2009-12–2026-03 | 196 | 1.015 | -0.030 | 0.211 | 0.718 | 68% | 71% | 41% | -0.41 to -0.09 |
| 12 | 2010-06–2025-09 | 184 | 0.977 | +0.045 | 0.130 | 0.820 | 80% | 83% | 52% | -0.77 to -0.25 |

RMSE ratio < 1 and Clark-West p < 0.05 would mean the ECT beats the drift benchmark. 'hit vs drift' asks whether the model gets the direction of the surprise relative to drift right.

### Full-sample predictive regressions

| h | β (Hodrick) | t (Hodrick 1B) | p | non-overlapping β median [min, max] | t median |
|---|---|---|---|---|---|
| 1 | -0.045 | -2.14 | 0.033 | -0.045 [-0.05, -0.05] | -2.05 |
| 3 | -0.119 | -1.86 | 0.062 | -0.118 [-0.13, -0.12] | -1.49 |
| 6 | -0.221 | -1.92 | 0.055 | -0.212 [-0.30, -0.13] | -1.34 |
| 12 | -0.434 | -1.89 | 0.058 | -0.435 [-0.59, -0.29] | -1.26 |

Regime-conditional (h=12, filtered P(stress)): α_calm -0.227 (p=0.435), α_stress -0.319 (p=0.370).

## Current ECM forecast

h=12m from 2026-09: ECT +0.132, α -0.434, const +0.071 → predicted Δlog INR +1.3% (drift alone +3.4%). Estimated on all realised targets; only as credible as the backtest above.

## Data revisions

The headline was re-run on the earlier RBI vintage (DBIE Excel files in data/raw, ending Oct 2025, Feb 2026, Mar 2026, Apr 2026), preferring it wherever both vintages have a value. Series revised beyond the 0.5% tolerance: bop.capital_account, bop.current_account, bop.fdi_bop, bop.loans, bop.merch_balance, fdi_usd_mn, fpi_usd_mn, imports_usd_mn, neer.

Point-in-time composite readings changed in 30 of 267 months (Jul 2004–Sep 2026): mean absolute change 0.014 pp, largest 0.47 pp (Jun 2026); by component, REER 0.000 pp and FEER 0.024 pp on average. Latest common month Sep 2026: +14.59% on the earlier vintage, +14.14% now. This is a lower bound on the revision effect (the earlier files are themselves partly revised); `python -m inrfv.vintages run <git-rev>` re-runs any committed vintage.

US CPI inflation: revised series with a fixed lag (ALFRED needs FRED_API_KEY; see data/alfred.py).

## Diagnostics

- BEER Engle-Granger (4 vars, n=308): stat -1.30, 5% critical -4.13, p = 0.975.
- Johansen PPP [log INR, log CPI India, log CPI US]: rank 0 of 3 (sequential trace, 5%, k_ar_diff=1, n=319).
- DXY splice: ratio 1.1937; log change at seam 2006-01: -2.40%.
- India CPI: official MOSPI CPI-Combined (inflation as published at the time). Segments: CPI-IW chained 1988-10–2010-12; MOSPI 2012 back series x LF 2011-01–2012-12; MOSPI 2012 x LF 2013-01–2025-12; MOSPI 2024 (chained) 2026-01–2026-08. Linking factor 2012→2024 0.5267 (2025 overlap ratio 0.5267); CPI-IW 1982→2001 factor 4.63. Inflation vs the old OECD series: corr 0.966, mean |diff| 0.41pp.
- India policy rate source: FRED IRSTCI01INM156N (overnight call rate).
- Call rate vs RBI repo rate (2008-06–2026-07): mean gap +0.32pp, mean |gap| 0.68pp, corr 0.800.
- FPI series: legacy FII before 2011-03, BoP net portfolio after.

## RBI data sources

RBIH Data API merged with DBIE Excel (later vintage preferred). API fetched 2026-10-01T09:14:35+00:00, mirror loaded 2026-10-01T09:08:30.

| Series | API range | Excel range | Later vintage | Overlap | Revised | Unexpected diffs |
|---|---|---|---|---|---|---|
| inr_usd | 1992-03–2026-06 | 1992-03–2026-04 | api | 410 | 0 | 0 |
| reer | 2004-04–2026-07 | 2004-04–2026-04 | api | 265 | 0 | 0 |
| neer | 2004-04–2026-07 | 2004-04–2026-04 | api | 265 | 1 | 0 |
| fx_reserves_usd_mn | 1951-03–2026-08 | 1990-03–2026-02 | api | 430 | 0 | 0 |
| exports_usd_mn | 1990-04–2026-06 | 1990-04–2026-03 | api | 432 | 0 | 0 |
| imports_usd_mn | 1990-04–2026-06 | 1990-04–2026-03 | api | 432 | 4 | 0 |
| fdi_usd_mn | 2011-03–2026-06 | 2011-03–2026-03 | api | 181 | 12 | 0 |
| fpi_usd_mn | 2011-03–2026-06 | 2011-03–2026-03 | api | 181 | 3 | 0 |
| bop.current_account | 1990-04–2025-07 | 2000-04–2025-10 | xlsx | 102 | 2 | 0 |
| bop.merch_balance | 1990-04–2025-07 | 2000-04–2025-10 | xlsx | 102 | 1 | 0 |
| bop.private_transfers | 1990-04–2025-07 | 2000-04–2025-10 | xlsx | 102 | 0 | 0 |
| bop.capital_account | 1990-04–2025-07 | 2000-04–2025-10 | xlsx | 102 | 2 | 0 |
| bop.fdi_bop | 1990-04–2025-07 | 2000-04–2025-10 | xlsx | 102 | 2 | 0 |
| bop.portfolio_bop | 1990-04–2025-07 | 2000-04–2025-10 | xlsx | 102 | 0 | 0 |
| bop.loans | 1990-04–2025-07 | 2000-04–2025-10 | xlsx | 102 | 1 | 0 |
| bop.banking_capital | 1990-04–2025-07 | 2000-04–2025-10 | xlsx | 102 | 0 | 0 |
| bop.reserve_change | 1990-04–2025-07 | 2000-04–2025-10 | xlsx | 102 | 0 | 0 |

## Data warnings

- REER anchor fundamentals are not cointegrated with the REER (Engle-Granger p=0.85); the anchor is reported, not relied on.
- BEER residuals are not cointegrated (Engle-Granger p=0.98); treat the BEER fair value as descriptive.

## Series end dates (reference month)

inr_usd 2026-09, reer 2026-07, neer 2026-07, fx_reserves_usd_mn 2026-08, exports_usd_mn 2026-06, imports_usd_mn 2026-06, fdi_usd_mn 2026-06, fpi_usd_mn 2026-06, dxy 2026-09, cpi_us 2026-08, fed_funds_rate 2026-08, vix 2026-09, us_10y_yield 2026-08, brent 2026-09, fed_balance_sheet 2026-09, india_stir 2026-07, cpi_india 2026-08, cpi_india_yoy 2026-08, india_policy_rate 2026-07, india_repo_rate 2026-09, india_wacr 2026-03, fwd_premium_1m 2026-06, fwd_premium_3m 2026-06, fwd_premium_6m 2026-06, rbi_net_purchase_usd_mn 2026-07, rbi_fwd_book_usd_mn 2026-07, rbi_intervention_usd_mn 2026-07

## Charts

![fair_value.png](fair_value.png)
![oos_12m.png](oos_12m.png)
