# Data refresh 01 Oct 2026

Run `20261001-092902` · as of **2026-08**

## Headline

Composite misalignment +12.4% → **+12.4%** (2026-08 → 2026-08); fair value 84.91 → **84.91**; spot 95.44 → 95.44. Change in the ECT by component: REER component +0.0pp, FEER +0.0pp.

## Gates

- All hard gates passed.
- warning: INR/USD uses rescaled FRED EXINUS for 2026-05, 2026-07, 2026-08 (RBI data missing; typical RBI-FRED gap 0.31%).
- warning: fx_reserves_usd_mn has missing months inside its range: 2026-04.
- warning: Latest BoP quarter is Oct 2025 (quarter start); the next one was due by Jul 2026. Download a fresh BoP file from DBIE or wait for the RBIH API to update.
- warning: REER anchor fundamentals are not cointegrated with the REER (Engle-Granger p=0.85); the anchor is reported, not relied on.
- warning: BEER residuals are not cointegrated (Engle-Granger p=0.98); treat the BEER fair value as descriptive.

## Data changes

No cached series changed.

