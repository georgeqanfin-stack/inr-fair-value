# Manually sourced inputs

Files here cannot be fetched programmatically, or are kept as an independent check
on an automatic source. Each must state its source.

## `mospi_cpi_2024base.csv`
All-India CPI (General, Combined), base 2024 = 100, Jan 2025 – Aug 2026.

**Since v0.9 this file is a cross-check and fallback, not the primary source.** The
pipeline reads the same series from the RBI Bulletin CPI table ("CPI - 2024=100 (All
India)", via the RBIH Data API, cached in `data/raw/dbie/cpi_2024base.csv`). It warns
if the two differ by more than 0.015 in any month, and uses this file only for months
the API does not have yet. The two matched in all 20 months when the switch was made.

Source: MOSPI, *Press Release of CPI for August 2026* (14 Sep 2026), Annexure IV
"All India Combined (General) level index and inflation", cross-checked against the
January, March, April, June and July 2026 releases:
https://www.mospi.gov.in/themes/product/9-consumer-price-index-cpi

- Verified 1 Oct 2026: all values Jan 2025 – Apr 2026 match Annexure IV exactly.
  May–Aug 2026 were added from the same table.
- Aug, Sep and Oct 2025 are genuinely all 103.74 (the food index moves normally in
  those months: 104.49, 104.12, 103.94). They are recorded as verified in
  `config/default.toml` → `[data_checks] verified_flat_runs`.
- Jan 2026 was 104.46 in the first (provisional) release and 104.45 once final.
- Aug 2026 is provisional; update it when the September 2026 release comes out.

This file is the 2025+ segment of the official India CPI. Earlier segments (CPI 2012 =
100 and CPI-IW) come from the RBIH Data API, and they are linked with MOSPI's official
factor 0.5267 (January 2026 release; the pipeline measures 0.52673 over 2025).
See `[cpi_india]` in the config and the README.

## `rbi_policy_repo_rate.csv`, `rbi_repo_rate_changes.csv`
RBI policy repo rate. `rbi_repo_rate_changes.csv` lists every change with its
effective date; `rbi_policy_repo_rate.csv` is the monthly series (rate in force at
month end, month-start dates), Jun 2008 – Sep 2026.

Source: RBI *Handbook of Statistics on the Indian Economy 2025-26* (31 Jul 2026),
Table 40, "Major Monetary Policy Rates and Reserve Requirements"
(https://rbi.org.in/scripts/PublicationsView.aspx?id=23865). The last change is
5.25% effective 5 Dec 2025; the Feb, Apr, Jun and Aug 2026 MPC meetings kept it
unchanged. This edition starts in 2008. Extend backwards from an older edition if needed.

The pipeline uses the overnight call rate by default (full sample, pairs with Fed
funds) and reports how closely it tracks the repo rate. Set
`india_policy_source = "repo"` in the config to use the repo rate from Jun 2008,
with the call rate before.

## `imf_ca_norm_india.csv`
India's current-account norm (% of GDP) from the IMF External Balance Assessment,
one row per publication: `available` is the month the norm became public.
`assessed` is the year or fiscal year the IMF assessed, and `se` is the standard
error (0.7 as stated in the 2024 and 2025 Article IVs; also used for earlier rows).
Values were read from:
- the IMF "EBA estimates" tables at https://www.imf.org/external/np/res/eba/data.htm
  (Table 1, "CA Norm" column; 2013–2015 and 2017–2024 assessments)
- the India Article IV staff reports: CR 13/37, 16/75, 25/54 and 25/314

Each row was checked against the table's own arithmetic (cyclically adjusted CA −
norm = total gap). The vintage assessing 2016 (published 2017) is not online.
Publication months are the External Sector Report release months (July; Aug in
2020 and 2021) and the Article IV publication months. Add a row each year when the
new External Sector Report comes out. The 2026 row (−2.3, s.e. 0.6, FY2025/26) is from
the 2026 External Sector Report, published 30 Jul 2026, Chapter 2, Table 2.11
(India). The refresh warns from each August until that year's row is added.

## Legacy FII flows (`../parsed_fpi_inr.csv`)
Monthly net FII investment in INR crore, Jan 2000 – Jun 2025, parsed by the legacy
notebook from an RBI workbook that was later overwritten. It is the only surviving
copy, so it is kept as a raw input and used for months before Mar 2011; from Mar 2011
the BoP net portfolio series (`rbi_fpi_flows.xlsx`) is used.
