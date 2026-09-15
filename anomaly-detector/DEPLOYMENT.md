# Deployment

The stack has a React/Nginx frontend, FastAPI API, and one background worker.
API and worker share the `anomaly-data` volume. SQLite stores upload metadata and
job status; reports and full findings are stored on disk.

```sh
cp .env.example .env
docker compose up --build -d
```

Use Docker Compose 2.24 or newer for optional `.env` syntax. Frontend:
`http://localhost:8080`; API: `http://localhost:8000`. Retain the data volume.

## Capacity

| Setting | Default | Meaning |
|---|---:|---|
| `ANOMALY_MAX_FILE_BYTES` | `68719476736` | 64 GiB per file. Set `0` for no configured size ceiling. |
| `ANOMALY_BATCH_ROWS` | `5000` | Rows processed together; allowed up to 100,000. |
| `ANOMALY_BATCH_CELLS` | `100000` | Cells per batch; allowed up to 2,000,000. |
| `ANOMALY_MAX_RECORD_BYTES` | `4194304` | Record-size guard; giant individual records are rejected. |
| `ANOMALY_DISK_RESERVE_BYTES` | `1073741824` | Free disk space reserved during upload. |
| `ANOMALY_JOB_DIR` | `.data/jobs` | Shared uploads, queue and findings directory. |
| `ANOMALY_STORAGE_DIR` | `.data/anomaly_analyses` | Shared saved dashboard reports. |
| `MIZAN_ALLOWED_ORIGINS` | `*` | CORS origins; Compose sets the local frontend origin. |
| `GEMINI_API_KEY` | empty | Optional AI explanations. Bulk batches use local reports. |

Change `.env` and recreate API and worker. The default capacity accommodates a
45 GB/GiB file if disk is available. File size is independent of per-batch row/cell
guards: a large file is processed across many batches, with no total row cap.
The server reserves remaining upload bytes and checks disk space for each chunk.
Setting `0` does not bypass physical storage.

Plan storage for **raw upload + full findings + existing results + free space**.
Findings contain explanations and may be substantially larger than source rows.
Output disk exhaustion visibly fails the job; partial success is not published.
CPU, column count, anomaly density and disk I/O affect runtime and memory.
RAM holds parser records and batches, not the complete source. A size setting is
not hardware certification: load-test representative data before depending on
45 GB production throughput.

## Upload and recovery

- The browser sends 8 MiB chunks. Nginx's 65 MiB per-request limit remains
  sufficient for a 45 GB file; a single giant HTTP request is not used.
- Resume a paused upload by selecting the same original file. Its ID and file
  metadata are retained in the browser. Do not edit the file while resuming.
- After upload, a durable queue feeds the worker. The progress panel reconnects
  after refresh; processing continues when the browser closes.
- Run one worker per shared directory; an OS lock prevents a second worker.
  A worker restart replays interrupted analysis from its uploaded source, without
  resending upload bytes. This is replay recovery, not a mid-batch checkpoint.
- Successful jobs remove raw source and retain reports/full findings. Cancel
  unused uploads to release reserved disk. Failed jobs retain source and partial
  evidence until cancelled or replaced by a retry.
- CSV/JSONL parse incrementally. Large JSON uses the
  [ijson streaming parser](https://github.com/ICRAR/ijson) and requires an array
  of objects or a `data`, `rows`, `records`, or `items` array. Single-object JSON
  remains supported by the small-file endpoint. Use UTF-8 and at most 2,000
  distinct columns.

## Detection scope

Bulk processing uses **independent batch baselines**. Every record is checked,
but duplicates, rarity, numerical distributions and relationships across batch
boundaries are not evaluated. This is not a global model fitted on the complete
bank dataset. Batch size and ordering can change findings.

Reports state this limitation. The dashboard retains 300 top findings, 50 top
risky rows and bounded chart samples; aggregate counts cover all batches.
Column profiles/overview histograms describe the first batch only. Numeric charts sample
across batches and omit a misleading global IQR band.
**Download all findings (JSONL)** includes every finding, global row numbers and
batch ranges. A malformed later record fails the whole job rather than presenting
earlier batches as complete results.

The separate Statistical exploration view computes box plots, IQR histograms and
correlations from a uniform reservoir of up to 2,000 rows across the entire file.
This is approximate descriptive evidence, not a global anomaly model. The UI
labels sample counts and distinguishes IQR outliers from existing model flags.
Additional flagged rows can appear in scatter plots but never bias the statistical
sample. Plots cover up to eight numeric columns selected from the first batch.

## Preprocessing configuration

| Variable | Default | Policy |
|---|---|---|
| `ANOMALY_PREPROCESSING_PROFILE` | `auto` | `auto`, `generic`, or `bank_marketing`. Auto recognizes the full 21-column Bank Marketing schema. Explicit Bank Marketing mode rejects incompatible schemas. |
| `ANOMALY_EXCLUDED_COLUMNS` | empty | Comma-separated column names excluded from model features. |
| `ANOMALY_TARGET_COLUMNS` | `target,label,is_anomaly,is_fraud` | Comma-separated outcome columns excluded from models. Set empty to disable generic name-based target exclusions. Bank Marketing also excludes `y`. |
| `ANOMALY_RATIO_PAIRS` | `[]` | JSON pairs of meaningful numeric columns, for example `[["qty","amount"]]`. Only pairs among the relationship detector's first eight eligible numeric columns are evaluated. |

Preprocessing runs before each detector invocation, including every bulk batch.
Whitespace is trimmed; blank, `unknown`, `null`, `none`, `nan` and `n/a` values are
recognized as missing (case-insensitive). Category case and identifier leading
zeros are preserved. Safe thousands grouping and currency prefixes are parsed;
ambiguous numbers such as `1,2` are not guessed as `12`. Mixed currencies or a
mixture of percentage/plain representations exclude that feature pending an
explicit unit mapping. Year-first dates are validated and standardized; ambiguous
day/month formats are retained rather than guessed.

Rows and extreme values are retained. Missing/invalid numerical values are
skipped, never median-filled. KNN considers features with at least 80% available
values, scales with median/MAD, and skips incomplete rows on its selected features.
The original source values are included alongside prepared values in findings;
the JSON report also contains bounded transformation examples, not a complete
cell-by-cell audit. Existing bulk raw-source cleanup rules still apply.

The Bank Marketing profile follows the official `bank-additional-names.txt` in
[UCI's source archive](https://archive.ics.uci.edu/static/public/222/bank+marketing.zip).
It represents `pdays=999` as not applicable rather than a numeric anomaly or missing
quality defect. The subscription target and five macroeconomic context columns
are excluded from individual-record models. These rules do not certify fraud
detection accuracy, and unrelated schemas use generic preparation.

`data_quality_score` now reports the percentage of known, valid cells, excluding
documented not-applicable cells from the denominator. Exact original duplicate
counts are reported separately. Bulk quality counts aggregate all batches;
duplicate checks, inferred roles, and model baselines remain batch-relative.
Past reports retain their previous pipeline/scoring version until reanalyzed.

## Local development commands

Run in separate terminals from `backend/` with the same environment:

```sh
python -m uvicorn app.main:app --reload
python -m app.large_data
```

Run `npm run dev` from `frontend/`. Without the worker, bulk jobs remain queued.
Small files can still use the existing synchronous endpoint.
