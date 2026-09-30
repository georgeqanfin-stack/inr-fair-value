# Legacy notebooks (v0.1–v0.2): superseded

These notebooks are kept for history only. They are replaced by the `inrfv`
package (`python -m inrfv.run`) and should not be used for results:

- They use future data: two-sided HP filter, smoothed Markov probabilities,
  full-sample BEER and FEER parameters, and overlapping training targets.
- `01_data_build.ipynb` parses RBI files by column position. The raw files have
  since been re-downloaded in a new layout, so re-running it silently reads the
  wrong columns (INR/SDR instead of INR/USD) and fails to parse FPI flows.
- Cells were run out of order and overwrite shared files in `data/processed/`.

The FRED API key that used to be hardcoded here has been replaced with
`os.environ.get('FRED_API_KEY')`. The old key was exposed in plain text and
should be rotated at https://fredaccount.stlouisfed.org/apikeys.
