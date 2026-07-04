# INR/USD Hybrid Fair Value Model

A probabilistic equilibrium-corridor model for the Indian Rupee, combining four independent valuation approaches to estimate where INR/USD should trade and whether the current exchange rate is sustainable. The study covers January 2000 through April 2026, capturing the Global Financial Crisis, the 2013 taper tantrum, COVID-19, the 2022 Fed tightening cycle, and a live geopolitical oil shock driven by the US-Israel conflict with Iran (February 2026 onwards).

## Current Reading (April 2026)

| Model | Misalignment | Fair INR/USD | What It Measures |
|---|---|---|---|
| REER Structural | +8.7% undervalued | 86.06 | Long-run real equilibrium |
| FEER Static | +3.3% undervalued | 86.23 | External sustainability (−2.5% CAD norm) |
| FEER Conditional | −2.4% overvalued | 91.35 | What financing actually supports |
| BEER Short-run | +14.7% undervalued | 80.86 | Market-driven fundamental value |
| Composite ECM | +8.2% undervalued | 86.15 | Blended equilibrium (REER + FEER) |

Three models agree on fair value ≈ ₹86. The conditional FEER flips the sign — with FDI negative and only ECB loans providing stable capital, the financing environment supports a weaker fair value of ₹91.35. The 5.8pp financing premium measures how much capital-account stress distorts fair value beyond what fundamentals justify.

Markov regime probability: P(stress) = 0.78. The model classifies the current environment as a stress regime where equilibrium reversion historically breaks down.

## Data

### Sources

- **FRED (Federal Reserve Economic Data):** US CPI (`CPIAUCSL`), Fed Funds Rate (`FEDFUNDS`), Broad Trade-Weighted Dollar Index (`DTWEXBGS`), VIX (`VIXCLS`), 10-Year Treasury Yield (`GS10`), Brent Crude (`DCOILBRENTEU`), Fed Balance Sheet (`WALCL`), India Short-Term Interest Rate (`IRSTCI01INM156N`)
- **RBI DBIE:** INR/USD exchange rate, 40-currency REER (base 2015-16=100), foreign exchange reserves, merchandise trade, full Balance of Payments quarterly panel (current account, capital account, FDI, portfolio investment, ECB/loans, banking capital, reserve movements), monthly FPI/FDI flows from the BoP foreign investment table
- **World Bank:** GDP (India, US), GDP per capita, remittances
- **MOSPI:** India CPI (2024=100 base), spliced with OECD series via Jan-Mar 2025 overlap ratio

### Construction

The raw data pipeline is handled in `05_data_and_models.ipynb`. Key decisions:

- **Brent crude** uses monthly averages (not month-end) to avoid single-day outlier sensitivity. This matches the IMF convention the oil elasticity was validated against.
- **GDP** beyond the last World Bank observation (2024, $3.91T) is extrapolated using RBI's 6.9% real growth projection for FY2026-27 combined with a 4% GDP deflator, yielding 11.18% nominal growth. The extrapolation is converted to USD at each month's actual INR/USD rate, preserving the FX channel: when INR depreciates, USD-denominated GDP falls and %-of-GDP ratios widen correctly.
- **FPI flows** use RBI's BoP Net Portfolio Investment definition from March 2011 onward, spliced onto the earlier FII series at a seam that is invisible in the data (Feb 2011: −$854mn → Mar 2011: −$609mn). This gives a single consistent definition across the modeling window that ties directly to the BoP framework.
- **Brent normal** is fixed at $72 — the full modeling-window median (2004-2025), deliberately not rolling, to exclude the pre-2004 cheap-oil era and transient war/Ukraine spikes.
- The **BoP financing panel** (9 quarterly series) is extracted from RBI's Balance of Payments table to enable the conditional FEER norm. This is not available in standard FRED/WB pulls.

### Point-in-Time Lag Discipline

Every input carries its real-world publication delay to prevent look-ahead bias:

| Series | Lag | Rationale |
|---|---|---|
| INR/USD, REER, DXY, VIX, Brent, reserves, repo rate | 0 months | Daily/weekly, real-time |
| US CPI, India CPI, trade data | 1 month | BLS/MOSPI ~2 week publication delay |
| FPI/FDI monthly flows | 2 months | RBI Bulletin ~6-8 week lag |
| GDP, remittances | 3 months | Annual, post year-end |
| Full BoP quarterly panel | 6 months | Quarter-start marker + 3mo quarter + 3mo publication |

Derived ratios (CAD/GDP, FPI/GDP, real rate differential) are recomputed from the lagged raw inputs, not lagged independently. The lagged dataset (`master_v2_lagged.csv`) is used for all estimation and backtesting; the unlagged version (`master_v2.csv`) serves as a live-tracker reference.

## Models

### Model 1: REER Structural Anchor (`05_data_and_models.ipynb`)

Hodrick-Prescott filter (λ = 129,600 for monthly data) applied to RBI's 40-currency Real Effective Exchange Rate index to extract the long-run trend. Fair INR/USD is the spot rate adjusted by the ratio of actual REER to trend REER.

Sign convention throughout: positive misalignment = INR undervalued (weaker than fair).

Episode validation: GFC +6.9%, Taper +8.8%, COVID +1.4%, Fed tightening −0.3%.

### Model 2: FEER Sustainability Engine (`05_data_and_models.ipynb`)

Fundamental Equilibrium Exchange Rate with two norms:

**Static norm (−2.5% of GDP):** What exchange rate makes the current account deficit sustainable at a fixed target? Uses a locked REER semi-elasticity of −0.267 pp/1% (IMF-EBA validated, range −0.2 to −0.4) and an oil pass-through elasticity of −2.45 per log-point of Brent (re-estimated at −2.61, p < 0.0001, R² = 0.40, locked to prior for stability).

**Conditional norm (financing-adjusted):** What deficit can the current financing environment actually support? Constructed from the capital-account side of the BoP: stable financing = net FDI + medium-term ECB/loans. Private transfers (remittances) are excluded because they sit on the current-account side and are already reflected in the CAD figure.

The financing premium (gap between static and conditional FEER) measures capital-account stress directly. In Q3 FY26: FDI negative at −$3.7bn, only loans (+$13.3bn) keeping stable capital positive, overall BoP plugged by a $24.4bn reserve drawdown.

### Model 3: BEER + Regime Engine (`05_data_and_models.ipynb`)

Behavioural Equilibrium Exchange Rate: cointegrating OLS regression (Newey-West HAC standard errors, 6 lags) of log(INR/USD) on log(DXY), real interest rate differential, FPI/GDP, log(Brent), and VIX. R² = 0.852, residuals cointegrated (ADF p = 0.014). The Dollar Index alone explains 75% of INR variance; India-specific factors explain 42% of the remaining residual.

The regime engine has two layers:

1. **Oil × DXY matrix:** Four quadrants by median Brent ($68) and median DXY (105). The twin-pressure quadrant (high oil + strong dollar) averages +0.49%/month depreciation.

2. **Markov-switching model** (Hamilton-type, switching mean and variance): Calm regime (+0.06%/mo, σ = 0.77%, duration 7.1mo) and stress regime (+0.53%/mo, σ = 2.39%, duration 4.0mo). The March 2026 oil shock registers at P(stress) = 0.78.

### Model 4: Unified Error Correction Model (`06_unified_ecm.ipynb`)

Two-tier ECM testing whether deviations from the composite equilibrium predict future INR returns:

**Composite equilibrium:** 50/50 blend of REER fair value (monthly, real-time) and FEER static fair value (quarterly, shifted by 6-month publication lag and forward-filled). The BEER is excluded from the composite to avoid circularity — it uses the same drivers as the ECM's short-run dynamics.

**Stationarity gate:** The error correction term (ECT = log(INR) − log(composite fair)) is stationary (ADF p = 0.0000), confirming the equilibrium is valid and mean-reverting.

**Multi-horizon predictability:**

| Horizon | α | p-value | R² |
|---|---|---|---|
| 1 month | +0.017 | 0.566 | 0.002 |
| 3 months | −0.017 | 0.858 | 0.000 |
| 6 months | −0.093 | 0.542 | 0.007 |
| 9 months | −0.298 | 0.095 | 0.041 |
| 12 months | −0.450 | 0.002 | 0.073 |

Monthly predictability is absent (consistent with the Meese-Rogoff puzzle). At the 12-month horizon, the signal is highly significant: a 10% ECT predicts a 4.5% INR correction over the following year.

**Regime conditioning:** Error correction is regime-dependent. In calm periods, deviations revert (α_calm = −0.05 at 1-month, −0.30 at 6-month). In stress, they overshoot (α_stress = +0.06, positive). The unconditional monthly α ≈ 0 because these cancel.

**Out-of-sample stability:** The 12-month α is remarkably stable across all expanding estimation windows (range: −0.40 to −0.48, mean −0.45). It never flips sign — the strongest evidence against overfitting. Out-of-sample magnitude correlation: Pearson 0.49, Spearman 0.44.

**Limitation on directional accuracy:** The 92% out-of-sample directional hit rate is misleading — INR has depreciated in nearly every 12-month window from 2004 to 2025, so predicting "depreciation" every month would achieve similar accuracy. The model never predicts appreciation because the structural depreciation trend (constant ≈ +3.8%/year) dominates the reversion signal. The meaningful test is the magnitude correlation, not the directional hit rate.

## Repository Structure

```
inr-fair-value/
├── README.md
├── data/
│   ├── raw/                          # Source files (RBI xlsx, WB csv)
│   │   ├── rbi_inr_usd.xlsx
│   │   ├── rbi_reer.xlsx
│   │   ├── rbi_reserves.xlsx
│   │   ├── rbi_trade.xlsx
│   │   ├── rbi_cab.xlsx
│   │   ├── rbi_fpi_flows.xlsx
│   │   └── wb_gdp_india.csv
│   └── processed/                    # Model inputs and outputs
│       ├── master_v2.csv             # 52-column unlagged dataset (live tracker)
│       ├── master_v2_lagged.csv      # Point-in-time lagged dataset (backtest)
│       ├── phase2_equilibrium_v2.csv # REER structural anchor
│       ├── phase3_feer_v2.csv        # FEER sustainability + conditional norm
│       ├── phase4_beer_v2.csv        # BEER + regime classification
│       ├── beer_coefs_v2.json        # BEER regression coefficients
│       └── ecm_base.csv             # ECM dataset + forward returns
├── notebooks/
│   ├── 05_data_and_models.ipynb      # Data pipeline + Phases 2-4
│   └── 06_unified_ecm.ipynb          # Error correction model + backtest
└── outputs/                          # Charts (if generated)
```

## Requirements

```
python >= 3.10
pandas
numpy
statsmodels
scipy
openpyxl
fredapi
matplotlib
```

A FRED API key is required for the data refresh step. Get one free at https://fred.stlouisfed.org/docs/api/api_key.html.

## Usage

1. Place RBI DBIE files in `data/raw/` and set your FRED API key in the first cell of `05_data_and_models.ipynb`.
2. Run `05_data_and_models.ipynb` end to end. This refreshes all data sources, builds the master dataset with point-in-time lags, and estimates Models 1-3 (REER, FEER, BEER).
3. Run `06_unified_ecm.ipynb`. This constructs the composite equilibrium, estimates the ECM, runs the out-of-sample backtest, and produces the final four-model convergence dashboard.

The notebooks are designed to run sequentially. Notebook 06 depends on the output files from notebook 05.

## Methodology Notes

- **Why April 2026?** That is the latest month for which RBI publishes the INR/USD exchange rate at the time of analysis. FRED market series (DXY, VIX) extend to May-June 2026; RBI trade data extends to March 2026. The dataset has a ragged edge by design — each series ends where its source data ends, and we do not forward-fill across series.
- **Why exclude BEER from the composite ECM equilibrium?** The BEER regression uses the same short-run drivers (DXY, Brent, VIX, rates) as the ECM's Δ-terms. Including it in the composite would create circularity: the equilibrium would partially reflect the drivers we're trying to measure the deviation from.
- **Why is the REER semi-elasticity locked rather than re-estimated?** Monthly trade balance data is too noisy for reliable estimation of the REER-trade relationship (the monthly regression yields +0.08, wrong sign, p = 0.32). The −0.267 parameter is from a first-differenced quarterly specification validated against the IMF's External Balance Assessment range of −0.2 to −0.4. Structural elasticities don't shift with a few months of new data.
- **DXY in this model is DTWEXBGS** (the Fed's Broad Trade-Weighted Dollar Index, ~118-120 scale), not the ICE DXY (~99). They are different indices and should not be compared directly.
