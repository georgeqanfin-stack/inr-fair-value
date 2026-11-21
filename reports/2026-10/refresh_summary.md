# Data refresh 21 Nov 2026

Run `20261121-122314` · as of **2026-10**

## Headline

Composite misalignment +15.6% → **+15.6%** (2026-10 → 2026-10); fair value 82.64 → **82.64**; spot 95.52 → 95.52. Change in the ECT by component: REER component +0.0pp, FEER +0.0pp.

## Gates

- All hard gates passed.
- warning: MOSPI CPI ends Sep 2026 in both the RBI API and data/raw/manual/mospi_cpi_2024base.csv; Oct 2026 should be out. If the API lags, add it from https://www.mospi.gov.in/themes/product/9-consumer-price-index-cpi (Annexure IV).
- warning: Latest BoP quarter is Jan 2026 (quarter start); the next one was due by Oct 2026. Download a fresh BoP file from DBIE or wait for the RBIH API to update.
- warning: REER anchor fundamentals are not cointegrated with the REER (Engle-Granger p=0.85); the anchor is reported, not relied on.
- warning: BEER residuals are not cointegrated (Engle-Granger p=0.95); treat the BEER fair value as descriptive.

## Data changes

No cached series changed.

