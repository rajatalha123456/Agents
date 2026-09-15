# Verification — updated 11 September 2026

## Latest complete integration run

- **25 local tests passed**, including the frontend, OpenAI provider, all model adapters and the optional sequence model.
- **23 Docker tests passed**; the two optional PyTorch sequence tests were deselected in the tabular image.
- The Docker image was rebuilt with the frontend, OpenAI adapter, live connection checker and LLM-led synthetic demo command. Compose configuration validated; Docker defaults to host port 8018.
- The native frontend returned HTTP 200 at `http://127.0.0.1:8017/`; the backend `/health` returned `status: ok`.
- Live OpenAI verification remains pending: `.env` still has no `OPENAI_API_KEY`, and `LLM_PROVIDER=none`. The connection checker correctly reports this as not ready. No exposed chat key was used.
- A browser could not be opened automatically because the browser-control tool reported no browser available. HTTP checks passed; browser interaction QA is not claimed.
- See `ACCEPTANCE.md` for the delivered feature checklist and production limits.

## Earlier verification history

- Local Python suite: **19 passed**, including all four tabular models, tree SHAP, sequence training and serialization, ensemble evaluation, temporal purging, tenant isolation, policy evidence, agent tool contracts, saved inference and HTTP onboarding.
- Docker suite: **17 passed**, with the two optional PyTorch sequence tests excluded because the base image contains tabular dependencies only.
- Docker image `member-risk-hardship:local` built successfully. Its default command started the API and `/health` returned `status: ok`. The temporary smoke-test container was stopped and removed.
- `docker compose config --quiet` succeeded.
- Live local demonstration: created a synthetic tenant, uploaded 1,600 historical rows, trained all four candidates, selected and persisted Logistic Regression, and successfully predicted a future synthetic record without retraining.
- Local service: `http://127.0.0.1:8017/docs`. Restart with `run.ps1` if the current process ends. Port 8000 was occupied by an unrelated process.

The initial sandbox test attempts could not read approved package installations, and an elevated retry encountered sandbox-owned temporary-directory permissions. The final successful local run used a fresh project-local temporary directory and access to the installed dependencies.

The live demo's held-out PR-AUC was 0.5816, ROC-AUC 0.8005 and Brier score 0.1359 on **synthetic data only**. These numbers are not production performance claims. The default gates are illustrative and require organization validation.

Real LLM calls have not been exercised: `LLM_PROVIDER=none`. Scripted provider contract tests verify orchestration and grounding; they do not establish real-model reliability. Configure a tool-capable Ollama model as described in the README.

This delivery is a functioning backend MVP. The README lists remaining production work, including centralized identity/roles, encrypted deployment storage, distributed jobs/rate limits, expanded drift/fairness controls, semantic data governance and organization-specific validation.

## Local frontend addition

Added a same-origin operations frontend at `/`, served with the backend on port 8017. It connects to authenticated dataset, training, model, prediction, policy and audit endpoints. JavaScript passed `node --check`. The frontend route/isolation test and five OpenAI-provider contract tests passed together (6 passed). HTTP checks verified the running frontend and backend. Browser interaction/visual QA was not performed. The Docker rebuild required at this stage is now completed, as recorded above.
