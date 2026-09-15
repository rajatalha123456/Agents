# Mizan â€” Anomaly Dashboard

Upload any CSV or JSON file and get model-ranked, explained anomalies: a
decision summary, severity breakdown, a risk-score scatter plot, and a
click-to-explain table for every flagged row.

## How it works

- **Backend** (`backend/`): FastAPI service (`app/routers/generic_anomaly.py`)
  that profiles the uploaded file's columns, scores rows with a small ensemble
  of statistical/ML detectors (duplicates, type mismatches, robust outliers,
  ratio/correlation breaks, multivariate distance, rare categories and
  combinations), and optionally asks Gemini for a plain-language summary.
  Analyses are saved as JSON under `backend/.data/anomaly_analyses/` so recent
  files can be reopened.
- **Frontend** (`frontend/`): a single-page React/Vite dashboard
  (`src/pages/GenericAnomalyAgent.jsx`) â€” upload, charts, and an anomaly
  table with inline explanations.

## Running locally

Backend:

```
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Frontend:

```
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/v1/*` to `http://localhost:8000`.

## Configuration

Copy `.env.example` to `backend/.env` and set `GEMINI_API_KEY` to enable the
AI summary and per-anomaly AI explanations. Without a key, the dashboard
still works â€” it falls back to a locally generated summary/explanation.

## Tests

```
cd backend
python -m pytest tests -q
```


Large files use resumable 8 MiB uploads and a durable background worker. Default
file capacity is **64 GiB**, configurable with `ANOMALY_MAX_FILE_BYTES`; `0`
removes the configured ceiling while disk checks still apply. There is no total
row cap on this path. CSV, JSONL and JSON arrays are parsed incrementally and
processed in bounded batches instead of loading the whole file into RAM.

Start the worker in a second backend terminal with `python -m app.large_data`,
or use Docker Compose, which starts it with shared persistent storage. The UI
shows upload/processing progress and reconnects to saved jobs. Complete finding
evidence is available as a streamed JSONL download.

Bulk baselines are **batch-relative**, not a global fit across the full file.
Cross-batch duplicates and patterns can be missed. Reports label this scope and
sampled charts. The synchronous endpoint keeps its 64 MiB, 100,000-row and
2,000,000-cell guards; the browser switches to bulk processing for larger files
or datasets exceeding those guards.

See [DEPLOYMENT.md](DEPLOYMENT.md) for storage, recovery and detection limitations.
A 45 GB production workload still needs a representative load test on the target
server; the capacity setting is not a throughput guarantee.

Statistical exploration adds selectable box plots, IQR-coloured histograms and
two-column scatter plots with Pearson correlation. Small-file statistics use all
rows. Bulk statistics use a uniform reservoir of up to 2,000 rows across the full
file, with the sample scope labelled in the UI. Extra flagged scatter points do
not influence quartiles, histogram counts or correlation. These exploratory
statistics do not replace the existing anomaly detectors.

Every new analysis now runs through `backend/app/preprocessing.py` before any
detector. It validates headers, normalizes whitespace and missing tokens, parses
unambiguous numeric/date formats, retains original evidence, and selects eligible
model features. No rows or extreme values are removed, and missing values are
not imputed. The dashboard shows preparation counts, excluded-column reasons,
original/prepared previews and transformation examples.

The full Bank Marketing schema selects its documented profile automatically:
`unknown` is missing, `pdays=999` is not applicable, and `y` plus macroeconomic
context fields are excluded from individual-record models. Generic datasets do
not inherit the `pdays` rule. Numeric ratio checks default to disabled; configure
meaningful pairs explicitly. The quality metric now measures known, valid cells,
independently of anomaly severity or dataset size. See [deployment settings](DEPLOYMENT.md).
