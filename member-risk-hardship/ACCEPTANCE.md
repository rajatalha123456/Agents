# Local MVP acceptance status

The local application is implemented and passes automated checks. Completion of a real OpenAI-led run is pending a configured replacement API key. Production banking readiness is a separate validation and deployment milestone.

| Specification area | Delivered | Validation / limit |
|---|---|---|
| Tenant creation and isolation | Authenticated tenant API, hashed tenant keys, scoped metadata and artifacts | Isolation and API tests |
| Historical uploads | CSV, XLSX, JSON; size/type checks | Parsing and API tests |
| Dataset understanding | Profiling, canonical mapping, missing values, label/sequence signals | Data and agent contract tests |
| Feature governance | Allowlist, protected/proxy flags, leakage blocking | Guardrail tests; semantic governance requires organization review |
| Model candidates | Logistic Regression, XGBoost, LightGBM, CatBoost | All four trained in tests and the synthetic API demo |
| Sequence model | CNN, bidirectional LSTM, attention and last-observation fusion | Local training and serialization tests; optional PyTorch install |
| Validation and calibration | Shared partitions, temporal purging, calibration partition, threshold selection | Temporal and metric tests |
| Model registry | Versioned artifacts, integrity hashes and production promotion | Persistence and versioning tests |
| Saved-model prediction | Single and batch APIs, tenant-specific preprocessing | Tests verify prediction never retrains |
| Explanations | Tree SHAP, logistic contributions, labelled ablation fallback | Tree SHAP tested for all three tree libraries |
| Hardship and policy | Conservative text signals, declared forms, configured support paths | Evidence and eligibility tests; no actions executed |
| Agent orchestration | Bounded tools with Ollama and OpenAI adapters | Tool-contract and OpenAI transport tests; live provider test pending |
| Monitoring and audit | Audit events, numeric drift screening, offline fairness utility | Basic monitoring only; full production drift/governance remains separate |
| Frontend | Organization connection, upload/mapping, training status, model review, assessments, policies, audit | Static syntax and authenticated HTTP tests; browser interaction QA not performed |
| Docker | Rebuilt image includes frontend and OpenAI adapter; configurable host port | Image build and container test suite |
| Documentation and examples | README, synthetic datasets, direct demo, agent demo, provider check | Runnable commands included |

## Pending live integration

Set these fields in `.env` without sharing the secret in chat:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=your-replacement-key
OPENAI_MODEL=gpt-4.1-mini
ALLOW_EXTERNAL_LLM=true
```

Run `python -m scripts.check_llm`, restart `run.ps1`, then run `python -m scripts.demo --agent` with `RISK_API_URL=http://127.0.0.1:8017`. The connection test sends only a synthetic marker; the agent demo uses synthetic financial records and makes billed API requests.

## Deployment limits

This release uses local files, SQLite, one worker and an in-process training queue. Central identity/roles, key rotation, encryption infrastructure, a distributed queue, richer monitoring, independent security review, and validation on representative institutional data are still needed for a production deployment. No tested synthetic metric establishes production lending suitability.
