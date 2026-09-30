# Manually sourced inputs

Files here cannot be fetched programmatically. Each must state its source.

## `mospi_cpi_2024base.csv`
All-India CPI (General, Combined), base 2024 = 100, Jan 2025 – Aug 2026.

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

MOSPI's official linking factor from CPI 2012=100 to CPI 2024=100 (Combined) is
0.5267 (January 2026 release). The pipeline instead ratio-splices onto the OECD CPI
for India (`INDCPIALLMINMEI`, a different base, ends Mar 2025) over Jan–Mar 2025.

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

## Legacy FII flows (`../parsed_fpi_inr.csv`)
Monthly net FII investment in INR crore, Jan 2000 – Jun 2025, parsed by the legacy
notebook from an RBI workbook that was later overwritten. It is the only surviving
copy, so it is kept as a raw input and used for months before Mar 2011; from Mar 2011
the BoP net portfolio series (`rbi_fpi_flows.xlsx`) is used.
