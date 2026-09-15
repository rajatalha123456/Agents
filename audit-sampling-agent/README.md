# Standalone Audit Sampling Agent

A standalone, audit-friendly agent that:

1. Understands incoming tabular data (CSV/JSON/JSONL)
2. Builds a risk-preserving preprocessing plan
3. Detects anomalies independently
4. Computes transaction/run/pool risk scores
5. Produces explainable risk reasons
6. Creates hybrid audit samples
7. Logs all sampling decisions
8. Supports auditor challenges and overrides

## Core principle

**Never delete suspicious data during preprocessing.**
Outliers, missing values, duplicates and rare values are preserved and converted into risk features.

## Architecture

Raw Data
→ Data Profiler / Planner
→ Risk-Preserving Preprocessing
→ Anomaly Engine
→ Risk Engine
→ XAI / Reason Engine
→ Pool / Run / Transaction Ranking
→ Hybrid Sampling
→ Audit Log
→ Challenge / Override

## Run

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:
- Swagger: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## Example CSV

```csv
transaction_id,run_id,pool_id,amount,timestamp,beneficiary,country,account_id
T1,R1,PAYMENTS,5000,2026-09-01 10:00:00,B1,PK,A1
T2,R1,PAYMENTS,800000,2026-09-01 02:10:00,B9,PK,A1
```

The system works with generic tabular data. If `transaction_id`, `run_id`, or `pool_id` are absent,
it creates safe fallback identifiers.

## Main endpoint

`POST /analyze`

Upload a CSV/JSON/JSONL file and choose:
- `sample_size`
- `high_risk_threshold`

Returns:
- ranked transactions
- ranked runs
- ranked pools
- selected audit sample
- preprocessing log
- sampling log id

## Challenge endpoint

`POST /challenge/{sampling_run_id}`

Stores auditor challenge/override with reason.

## Notes

The included planner is deterministic and schema-aware so the project runs without an external LLM.
`app/planner.py` defines the planner boundary. You can replace `HeuristicPlanner` with any LLM provider
while keeping the same JSON plan contract. The risk calculation itself remains deterministic and auditable.
