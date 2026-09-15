# Member Risk & Hardship Agent

A modular Python MVP implementing the supplied specification: tenant-scoped dataset onboarding, model comparison and calibration, persisted inference, model-derived explanations, hardship evidence, and approved support policies. The local frontend is available at **http://127.0.0.1:8017/** when started using `run.ps1`; the interactive API console is at **http://127.0.0.1:8017/docs**.

The frontend and backend share one process and origin. In the frontend, create an organization using `ADMIN_API_KEY` from your local `.env`, or connect using an existing organization ID and its access key. Save a new organization's access key when it is shown. Browser credentials stay in memory and clear on disconnect or page reload. Use Data & training to upload and review schemas, start training and follow progress; Overview to compare/promote models; Member assessment for saved-model predictions; Support policies to manage eligibility rules; and Audit trail for recent events. LLM controls remain disabled when the server reports no configured provider. Advanced sequence training, drift and batch inference remain available through the API.

This is an implementation for local evaluation and further production hardening. Synthetic demonstration performance is not evidence of suitability for lending decisions.

## Install and run

Python 3.11–3.13 is recommended. From this directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# Optional CNN + BiLSTM + attention support:
python -m pip install -r requirements-sequence.txt
Copy-Item .env.example .env
```

Set `ADMIN_API_KEY` in `.env` to a long random secret, then:

```powershell
python -m scripts.generate_demo
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

On this workspace, `powershell -ExecutionPolicy Bypass -File .\run.ps1` starts the API on **http://127.0.0.1:8017/docs**, using the project-local dependency directory if present. Port 8000 was already occupied on this machine. Pass `-Port 8000` to override. Set `$env:RISK_API_URL='http://127.0.0.1:8017'` when using the demo client with the launcher. A local `.env` has been generated with a random administrator key; it is excluded from source control.

In a second activated terminal, `python -m scripts.demo` creates a tenant, uploads synthetic history, trains all four tabular candidates, polls status, and makes a live prediction. It uses direct tools and does not require an LLM. Tenant API keys are displayed once; store them securely.

## LLM-led workflow

### OpenAI

Add a replacement key directly to the local `.env` file; never paste API keys into chat or commit them:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=your-replacement-key
OPENAI_MODEL=gpt-4.1-mini
ALLOW_EXTERNAL_LLM=true
```

Restart the API with `run.ps1` after changing configuration. OpenAI uses the same `/agent/onboard` and `/agent/predict` endpoints described below. The adapter calls the [Responses API function-calling interface](https://developers.openai.com/api/docs/guides/function-calling), sends only the existing aggregate/tool context, disables response storage with `store=false`, and validates each returned tool call locally. This setting does not claim zero data retention by the API provider. Credentials are sent only to `https://api.openai.com/v1/responses` and are never included in prompts or error messages.

Provider tests mock HTTP responses; live OpenAI access, billing and model availability must be checked using your replacement key. The key previously shared in chat was not saved or used.

After setting the key and the configuration above, verify the real connection without financial data:

```powershell
python -m scripts.check_llm
```

Restart the API, then run the complete synthetic LLM-led onboarding and prediction:

```powershell
$env:RISK_API_URL='http://127.0.0.1:8017'
python -m scripts.demo --agent
```

The `--agent` demonstration makes billed provider requests. Without that flag, the demo uses direct local tools.

### Ollama and the shared workflow

The actual orchestration layer is `app/agent.py`, with a provider interface and an Ollama implementation. It uses native structured tool calls for inspection, mapping, preprocessing, candidate training, evaluation, comparison, ensemble construction and persistence. Live agent prediction loads the saved model, obtains XAI and hardship/policy results, and selects supported reason references to assemble a grounded explanation. Uploaded values are never executed as code.

Configure a local Ollama server and a tool-capable model already available on that server:

```dotenv
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434
LLM_MODEL=your-installed-tool-capable-model
ALLOW_EXTERNAL_LLM=false
```

Use `POST /api/v1/tenants/{tenant_id}/agent/onboard` with `{"training": { ...training request... }}` instead of `/training/start`, and `/agent/predict` instead of `/predict`. No fake LLM is enabled when the provider is absent. Those endpoints report a configuration error until a provider is configured. Tests use a clearly identified scripted provider to verify tool contracts; that is not a live-model evaluation.

Non-loopback providers require `ALLOW_EXTERNAL_LLM=true` and HTTPS. Only schema, aggregate profiling, metrics, supported reason references and selected output context are sent. Raw rows, member identifiers and member messages stay local. Schema names and custom target descriptions may themselves contain organization information; use non-sensitive names. No external endpoint is configured by default.

Provider implementation reference: [Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling).

## API walkthrough (PowerShell)

Load the administrator key from your `.env` into the current session, or set `$env:ADMIN_API_KEY` securely before running these commands.

```powershell
$base = 'http://127.0.0.1:8000/api/v1'
$tenant = Invoke-RestMethod -Method Post -Uri "$base/tenants" -Headers @{'X-API-Key'=$env:ADMIN_API_KEY} -ContentType 'application/json' -Body '{"name":"Demo Bank","band_edges":[0.2,0.5,0.75]}'
$tenantId = $tenant.tenant_id
$tenantKey = $tenant.api_key
$headers = @{'X-API-Key'=$tenantKey}
$root = "$base/tenants/$tenantId"
```

Upload using `curl.exe` (not the Windows PowerShell `curl` alias):

```powershell
$dataset = curl.exe -s -H "X-API-Key: $tenantKey" -F "file=@sample_data/historical.csv" "$root/datasets/upload" | ConvertFrom-Json
$ref = @{dataset_id=$dataset.dataset_id} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$root/datasets/profile" -Headers $headers -ContentType 'application/json' -Body $ref
Invoke-RestMethod -Method Post -Uri "$root/datasets/map-schema" -Headers $headers -ContentType 'application/json' -Body $ref
$body = @{dataset_id=$dataset.dataset_id; target_column='arrears_flag'; target_definition='30+ DPD within next 90 days'; labels_confirmed=$true; candidate_models='auto'; enable_ensemble=$false} | ConvertTo-Json
$job = Invoke-RestMethod -Method Post -Uri "$root/training/start" -Headers $headers -ContentType 'application/json' -Body $body
Invoke-RestMethod -Uri "$root/training/$($job.job_id)" -Headers $headers
```

Poll the last command until `completed` or `failed`. For real datasets, confirm the outcome is **future** arrears and its observation window is complete before setting `labels_confirmed`. A current arrears flag alone does not establish that.

```powershell
$prediction = @{member_id='DEMO-LIVE'; features=@{loan_amount=400000; income=75000; late_payments=3; missed_payments=1; days_past_due=22}} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$root/predict" -Headers $headers -ContentType 'application/json' -Body $prediction
```

Policy creation:

```powershell
$policy = @{policy_id='HARDSHIP_04'; name='Temporary Payment Reschedule'; max_days_past_due=60; hardship_categories=@('temporary_income_disruption'); requires_human_approval=$true} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$root/policies" -Headers $headers -ContentType 'application/json' -Body $policy
```

For declared hardship, supply `declared_hardship_category` in a prediction or `declared_category` to `/hardship/support-options`. Text-only pattern matches are conservative **inferred signals** requiring confirmation; they never create declared eligibility. No action is executed, even for eligible policies. No support products exist until explicitly configured.

Additional routes: `/predict/batch` (up to 100 records), `/models`, `/models/promote`, `/audit`, `/monitoring/drift`, `/hardship/analyze`, `/policies`. Exact request schemas are in `/docs` and `/openapi.json`.

## Model and validation behavior

- Candidate adapters: Logistic Regression, XGBoost, LightGBM and CatBoost. All use the same partitions and feature pipeline. Class weighting is applied during fitting. Categorical values are encoded in a shared pipeline for comparability.
- Data is split into fitting, calibration, validation and untouched test partitions. Date-aware splits purge the configured future horizon at partition boundaries and exclude members shared with later partitions. No-date data uses documented stratified splits; repeated member rows are rejected unless properly prepared as histories.
- Numeric imputation, scaling and categorical encoding are fit only on fitting data. Calibration uses its own partition. Threshold selection and weighted model selection use validation data. Held-out test data is opened after selection and may reject deployment; it never chooses a new winner.
- Metrics include average precision (reported as `pr_auc`), ROC-AUC, recall, precision, F1, false-negative rate, confusion matrix, Brier score, calibration error, specificity, balanced accuracy and accuracy.
- Sigmoid (Platt on log odds) and isotonic calibration are supported. Separation follows [scikit-learn's calibration guidance](https://scikit-learn.org/1.6/modules/calibration.html).
- Threshold objectives: F1, minimum recall, minimum precision or configured error costs. Risk-band edges are separate tenant configuration; they do not replace the tuned binary threshold.
- A weighted probability ensemble can compete on validation. Its held-out PR-AUC must exceed its constituents to deploy. A failed ensemble test gate stops the job rather than choosing a different winner using the test set.
- Tree explanations use SHAP raw-margin contributions; logistic explanations use centered log-odds contributions. Sequence/ensemble explanations use explicitly labelled feature ablation. SHAP failures yield labelled ablation, never invented SHAP. Explanations describe associations, not causes or certainty of default.
- Artifact bundles persist preprocessing, calibration, schema mapping, features, reference data and model together. SHA-256 integrity is checked on load. Inference never retrains. Subsequent training versions are staged for explicit promotion.

## Sequence input

Install `requirements-sequence.txt`. Enable `enable_deep_sequence_model` and provide at least 200 members, each with at least six distinct dated `payment_month` observations. Each member contributes its last six observations, with the final row's future label and timestamp as the anchor. All history must be available by that timestamp. Members with less history are excluded; all candidates use the same remaining members and partitions. Tabular baselines consume the last observation. The sequence model uses Conv1D, bidirectional LSTM, attention, last-observation fusion and a sigmoid output. Numeric history and categorical encodings are learned only from training members.

Live requests for such an artifact require `history` records with the trained feature fields and `payment_month`, plus `features.prediction_date`. Future or duplicate history timestamps are rejected. The supplied current static values are not substituted into the saved sequence window.

## Tests and deployment

```powershell
python -m pytest -q
docker compose config
docker compose up --build -d
```

Compose exposes the frontend and backend together at `http://127.0.0.1:8018/` by default, so it can coexist with the native launcher on 8017. Set `RISK_PORT` in `.env` to choose another Docker host port.

The Docker image installs tabular dependencies. Add the optional sequence requirements to the image for deep models. It runs under a non-root user and stores all state in a named volume. Back up that volume; do not accept untrusted replacements for model artifacts.

## Current limits and production work

- This release includes a local operations frontend and an interactive API console; it is not a production banking portal.
- SQLite, local artifacts, an in-process training executor and in-memory rate limiting target a **single worker / single instance**. PostgreSQL, an external queue and shared rate limiting are required for scale. Restarted jobs fail visibly and must be resubmitted.
- Tenant credentials are hashed; administrator/provider secrets come from environment configuration. TLS termination, encrypted storage/secrets management, SSO, role separation, key rotation, retention controls and independent security review remain deployment responsibilities. Do not expose this MVP directly to the public internet.
- Feature governance is a conservative built-in allowlist. Suspected proxies and unknown fields are held out for review; there is no automatic proxy approval. Custom financial features require a reviewed code change. Alias and leakage detection cannot establish all semantic leakage or legal suitability.
- There is no arbitrary document execution, protected-trait inference, automated adverse action, label derivation from unlabeled history, automatic replacement on drift or external enrichment.
- Drift monitoring currently screens numeric mean shifts. The offline fairness utility reports group metrics on an explicitly supplied controlled audit dataset. Full prediction/performance/calibration drift, comprehensive fairness review and production validation remain organization-specific work.
- Free-text hardship extraction is a small conservative pattern extractor. A live LLM orchestrates its use; it does not infer protected characteristics or fabricate evidence. Ambiguous messages require review.
- Validate provider reliability and all models on representative, properly labelled organization data before operational use. A configured live LLM and Docker engine are needed to verify those integrations on the deployment host.

## Source layout

`app/agent.py` orchestration/provider; `data.py` profiling/mapping/validation; `training.py` gated lifecycle and evaluation; `models.py` model adapters/calibration/ensemble; `sequence.py` deep model; `inference.py` saved inference/XAI; `hardship.py` evidence/policies; `governance.py` drift/fairness; `store.py` metadata/registry/audit; `main.py` authenticated API. `scripts/` contains synthetic data generation and a runnable client demo. `tests/` exercises model, API, isolation, guardrail and agent contracts.
