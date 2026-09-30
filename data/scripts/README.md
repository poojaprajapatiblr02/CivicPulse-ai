# Data Scripts

From the project root, run:

```powershell
.\backend\.venv\Scripts\python.exe .\data\scripts\generate_data.py
```

Options: `--seed 42` and `--output-dir PATH`. The default destination is
`data/synthetic`, regardless of the working directory. This deliberately overwrites
only the four generated local CSV files, never cloud tables. No cloud access is needed.
BigQuery schema export and loading commands are in `docs/bigquery-setup.md`.