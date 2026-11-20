# Data refresh 20 Nov 2026

Run `20261120-080204` · as of **2026-10**

## Headline

Composite misalignment +15.7% → **+15.6%** (2026-09 → 2026-10); fair value 82.50 → **82.64**; spot 95.41 → 95.52. Change in the ECT by component: REER component -0.1pp, FEER +0.0pp.

## Gates

- All hard gates passed.
- warning: MOSPI CPI ends Sep 2026 in both the RBI API and data/raw/manual/mospi_cpi_2024base.csv; Oct 2026 should be out. If the API lags, add it from https://www.mospi.gov.in/themes/product/9-consumer-price-index-cpi (Annexure IV).
- warning: Latest BoP quarter is Jan 2026 (quarter start); the next one was due by Oct 2026. Download a fresh BoP file from DBIE or wait for the RBIH API to update.
- warning: REER anchor fundamentals are not cointegrated with the REER (Engle-Granger p=0.85); the anchor is reported, not relied on.
- warning: BEER residuals are not cointegrated (Engle-Granger p=0.95); treat the BEER fair value as descriptive.

## Data changes

| File | New obs | New range | Revised | Largest revision | Lost |
|---|---|---|---|---|---|
| dbie/exports_usd_mn.csv | 2 | 2026-07–2026-08 | 3 | 2026-04: 4.371e+04 → 4.253e+04 (2.70%) | 0 |
| dbie/fdi_usd_mn.csv | 1 | 2026-07–2026-07 | 3 | 2026-06: 2077 → -876.8 (142.21%) | 0 |
| dbie/fpi_usd_mn.csv | 1 | 2026-07–2026-07 | 0 |  | 0 |
| dbie/imports_usd_mn.csv | 2 | 2026-07–2026-08 | 3 | 2026-06: 7.082e+04 → 7.078e+04 (0.06%) | 0 |
| dbie/inr_usd.csv | 2 | 2026-08–2026-09 | 0 |  | 0 |
| dbie/neer.csv | 1 | 2026-08–2026-08 | 0 |  | 0 |
| dbie/reer.csv | 1 | 2026-08–2026-08 | 1 | 2026-07: 91.78 → 91.76 (0.02%) | 0 |
| fred/CLVMNACSCAB1GQEA19.csv | 1 | 2026-07–2026-07 | 126 | 2024-07: 2.856e+06 → 2.866e+06 (0.37%) | 0 |
| fred/CPIAUCSL.csv | 1 | 2026-10–2026-10 | 0 |  | 0 |
| fred/DCOILBRENTEU.csv | 30 | 2026-10–2026-11 | 0 |  | 0 |
| fred/DTWEXBGS.csv | 23 | 2026-10–2026-11 | 0 |  | 0 |
| fred/EXINUS.csv | 1 | 2026-10–2026-10 | 0 |  | 0 |
| fred/FEDFUNDS.csv | 1 | 2026-10–2026-10 | 0 |  | 0 |
| fred/GDPC1.csv | 1 | 2026-07–2026-07 | 0 |  | 0 |
| fred/GS10.csv | 1 | 2026-10–2026-10 | 0 |  | 0 |
| fred/IRSTCI01INM156N.csv | 3 | 2026-08–2026-10 | 0 |  | 0 |
| fred/RBBRBIS.csv | 3 | 2026-08–2026-10 | 96 | 2026-02: 114.3 → 114.3 (0.04%) | 0 |
| fred/RBCLBIS.csv | 3 | 2026-08–2026-10 | 97 | 2026-02: 107.4 → 107.3 (0.03%) | 0 |
| fred/RBCNBIS.csv | 3 | 2026-08–2026-10 | 199 | 2026-01: 89.52 → 89.58 (0.07%) | 0 |
| fred/RBCOBIS.csv | 3 | 2026-08–2026-10 | 91 | 2026-01: 123.4 → 123.3 (0.06%) | 0 |
| fred/RBCZBIS.csv | 3 | 2026-08–2026-10 | 47 | 2026-01: 129.1 → 128.9 (0.11%) | 0 |
| fred/RBHUBIS.csv | 3 | 2026-08–2026-10 | 63 | 2026-01: 116.7 → 116.6 (0.08%) | 0 |
| fred/RBIDBIS.csv | 3 | 2026-08–2026-10 | 210 | 2026-02: 92.29 → 92.34 (0.05%) | 0 |
| fred/RBILBIS.csv | 3 | 2026-08–2026-10 | 60 | 2026-03: 108.1 → 107.9 (0.19%) | 0 |
| fred/RBINBIS.csv | 3 | 2026-08–2026-10 | 88 | 2026-03: 90.99 → 91.32 (0.36%) | 0 |
| fred/RBKRBIS.csv | 3 | 2026-08–2026-10 | 231 | 2026-03: 85.07 → 85.11 (0.05%) | 0 |
| fred/RBMXBIS.csv | 3 | 2026-08–2026-10 | 104 | 2026-02: 141.7 → 141.7 (0.05%) | 0 |
| fred/RBMYBIS.csv | 3 | 2026-08–2026-10 | 196 | 2026-07: 106.1 → 106 (0.05%) | 0 |
| fred/RBPEBIS.csv | 3 | 2026-08–2026-10 | 71 | 2026-02: 110.4 → 110.3 (0.03%) | 0 |
| fred/RBPHBIS.csv | 3 | 2026-08–2026-10 | 199 | 2026-06: 98.07 → 98.15 (0.08%) | 0 |
| fred/RBPLBIS.csv | 3 | 2026-08–2026-10 | 49 | 2026-02: 130.3 → 130.2 (0.10%) | 0 |
| fred/RBROBIS.csv | 3 | 2026-08–2026-10 | 34 | 2026-02: 121.9 → 121.8 (0.08%) | 0 |
| fred/RBTHBIS.csv | 3 | 2026-08–2026-10 | 236 | 2026-07: 97.72 → 97.66 (0.06%) | 0 |
| fred/RBTRBIS.csv | 3 | 2026-08–2026-10 | 81 | 2026-03: 107.5 → 107.3 (0.12%) | 0 |
| fred/RBZABIS.csv | 3 | 2026-08–2026-10 | 152 | 2026-07: 114.5 → 113.7 (0.67%) | 0 |
| fred/VIXCLS.csv | 26 | 2026-10–2026-11 | 0 |  | 0 |
| fred/WALCL.csv | 6 | 2026-10–2026-11 | 0 |  | 0 |
