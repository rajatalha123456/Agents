# Disclosure Generator

Turns a cryptographically signed calculation run into a client-facing,
multilingual financial disclosure — with an LLM that is only ever allowed
to choose words, never numbers.

This repo has two parts: **`backend/`** (the actual Disclosure Generator —
Python/FastAPI) and **`frontend/`** (a React test console for exercising
it by hand; not part of the Disclosure Generator's own scope). All backend
commands below are run from inside `backend/`.

## 1. What it does

Given a **signed calculation run** (a JSON payload of NAV, returns,
allocation, fees, etc., produced by a calculation engine and signed with
Ed25519), this service:

1. **Verifies** the signature, freshness, and basic sanity of the run.
2. **Generates** a plain-language disclosure in English, Urdu, or Arabic
   using an LLM, working only from that verified payload.
3. **Independently re-checks** every number in the generated text against
   the payload with a deterministic, non-LLM numeric guard.
4. **Logs** every attempt — success or refusal — to an append-only audit
   trail.

If anything fails — bad signature, stale run, invalid allocation weights,
or a number in the generated text that isn't traceable to the payload —
the service **refuses** rather than guessing or silently fixing the data.

## 2. Architecture

```
Signed Calculation Run
        |
        v
Verify signature -> Check freshness -> Sanity validation   (backend/src/signing/verify.py)
        |  (any failure -> REFUSE, logged, LLM never called)
        v
Build prompt (payload + glossary + language template)      (backend/src/llm/generate.py, backend/src/llm/prompts/)
        v
Generate disclosure via Gemini client                        (backend/src/llm/client.py)
        v
Numeric guard: every generated number must exist            (backend/src/guard/numeric_guard.py)
in the verified payload -- retry once on failure, else REFUSE
        v
Append-only audit record                                    (backend/src/storage/run_store.py)
        v
Return disclosure / refusal                                 (backend/src/api/main.py)
```

Responsibilities are kept in separate modules on purpose: signing verification
never touches generation code, the numeric guard never touches the LLM, and
storage never touches API routing.

**Production topology** (this repo implements only the last box):

```
Calculation Engine -> Trusted Signing Service / HSM / KMS -> Signed Run Store
                                                                    |
                                                                    v
                                                    Disclosure Generator API (this repo)
```

The Disclosure Generator never generates or holds production signing keys —
see `backend/src/signing/sign.py`'s docstring and
`backend/scripts/generate_dev_keys.py`.

## 3. Installation

All commands in this section run from inside `backend/`.

### Python environment

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### Get a Gemini API key

This service uses Google's Gemini API as its sole LLM backend — no local
model to install or run. Get a key from
https://aistudio.google.com/apikey.

### Environment configuration

```bash
cp .env.example .env
```

Edit `.env` and set `GEMINI_API_KEY` to the key you just created — the API
will refuse to generate disclosures without it (verification/refusal still
works, since the LLM is only reached after verification passes). See
`.env.example` for every other variable; the two that matter most for a
real deployment are `MAX_RUN_AGE_SECONDS` (freshness window) and
`PUBLIC_KEY_PATH` (must point at the key your actual signing service uses).

### Generate development keys

```bash
python scripts/generate_dev_keys.py
```

Writes `backend/keys/dev_private_key.pem` and `backend/keys/dev_public_key.pem`.
**Local development/testing only** — production keys belong to your
signing service/HSM/KMS, never to this application. `keys/*.pem` is
gitignored.

## 4. Running the API

```bash
cd backend
uvicorn src.api.main:app --reload
```

Interactive docs at `http://localhost:8000/docs` (if that port is taken,
run with `--port 8001` or similar — and update `VITE_API_BASE_URL` in
`frontend/.env` to match, see §6).

## 5. API

### `GET /health`

```json
{"status": "ok"}
```

### `POST /disclosures/generate`

Request body: `{"signed_run": {...}, "language": "en" | "ur" | "ar"}`.

**Example request** (see `backend/tests/fixtures/sample_signed_run.json`
for a full worked example signed with the dev keypair):

```json
{
  "signed_run": {
    "run_id": "RUN-0001",
    "payload": {
      "account_id": "ACC-1001",
      "account_name": "Jane Doe",
      "currency": "USD",
      "period_start": "2026-06-01",
      "period_end": "2026-06-30",
      "nav": 1050000.75,
      "opening_balance": 1000000.0,
      "closing_balance": 1050000.75,
      "return_percent": 5.0,
      "allocation": [
        {"category": "Equities", "weight_percent": 60.0},
        {"category": "Fixed Income", "weight_percent": 40.0}
      ],
      "fees": [{"name": "Management Fee", "amount": 250.5, "currency": "USD"}]
    },
    "signature": "<base64 Ed25519 signature>",
    "signature_algorithm": "Ed25519",
    "signed_at": "2026-09-09T11:01:31.483928Z"
  },
  "language": "en"
}
```

**Example success response** (HTTP 200):

```json
{
  "run_id": "RUN-0001",
  "language": "en",
  "status": "success",
  "disclosure": "For the period 1 June 2026 to 30 June 2026, ...",
  "verification": {"signature_valid": true, "freshness_valid": true, "sanity_valid": true},
  "reason": null
}
```

**Example refusal response** (HTTP 422):

```json
{
  "run_id": "RUN-0001",
  "language": "en",
  "status": "refused",
  "disclosure": null,
  "verification": {"signature_valid": false, "freshness_valid": true, "sanity_valid": true},
  "reason": "verification failed: signature verification failed (payload may have been tampered with)"
}
```

No stack traces, keys, or internal detail are ever included in a response.

### Dev tools: `POST /dev/sign`

Only mounted when `ENABLE_DEV_TOOLS=true` (the default). Signs a caller-
supplied payload with the local dev private key and returns a full
`SignedRun` — this is what lets the test frontend (below) produce validly
signed runs without ever holding a private key in browser JS.

**Never enable this outside local development.** Anyone who can reach it
can forge validly-signed runs. Set `ENABLE_DEV_TOOLS=false` in any shared,
staging, or production environment.

## 6. Frontend (test console)

`frontend/` is a small React + Tailwind app for exercising the API by
hand: fill in a payload, sign it, optionally tamper with the signed JSON
(corrupt the signature, backdate `signed_at`) to exercise refusal paths,
pick a language, and see the disclosure or refusal rendered — including
RTL layout for Urdu/Arabic.

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL, defaults to http://127.0.0.1:8001
npm run dev
```

Open `http://localhost:5173`. It talks to the backend via CORS (see
`CORS_ALLOWED_ORIGINS` in `backend/.env.example`) — start the backend
first (§4). If you run the backend on a different port than 8001 (e.g.
because something else already occupies 8000 or 8001 on your machine),
update `VITE_API_BASE_URL` in `frontend/.env` to match.

The frontend is purely a manual testing aid — it is not part of the
Disclosure Generator's own scope or deployment.

## 7. Running tests

```bash
cd backend
pytest tests/ -v
```

This runs signature/freshness/sanity tests, numeric guard tests (including
formatting edge cases and prompt-injection cases), and generation
orchestration tests — all with the LLM call mocked, so they run offline
and deterministically.

A separate, live regression suite runs the real configured LLM against a
synthetic golden fixture set (`backend/tests/fixtures/golden/`, see its
README):

```bash
pytest tests/test_golden_regression.py -v          # first 5 fixtures
GOLDEN_FULL_RUN=1 pytest tests/test_golden_regression.py -v   # all 20
```

It's skipped automatically if `GEMINI_API_KEY` isn't configured.

## 8. The numeric guard

The most important property of this system: **the LLM only ever chooses
words.** Every number that ends up in the final text must already exist,
verbatim, in the signed payload.

`backend/src/guard/numeric_guard.py` enforces this independently of the LLM:

- Extracts every number from the payload (recursively, including numbers
  embedded in free-text fields) and every number from the generated text.
- Strips thousands separators and a trailing `%`, then compares values as
  `Decimal` — so `"1,050,000.75"`, `"1050000.75"`, and `"1050000.750"` are
  all recognized as the same value.
- Any number in the generated text that isn't in that payload set fails
  the check — no exceptions, no LLM adjudication.
- On failure, generation retries **exactly once** with the same verified
  payload; a second failure causes a refusal.

See the module docstring for the full extraction/normalization rules.

## 9. Security model

- **Fail closed.** Any verification or numeric-guard failure means no
  disclosure is returned — ever.
- **LLM output is untrusted** until the numeric guard independently
  confirms it.
- **Payload text is data, never instructions.** The system prompt
  (`backend/src/llm/prompts/system_prompt.txt`) explicitly tells the model
  to treat every payload field as untrusted data and ignore any embedded
  instructions (see `backend/tests/test_generation.py`'s prompt-injection
  tests and
  `backend/tests/test_numeric_guard.py::test_prompt_injection_number_in_field_is_available_but_neutral`).
- **The signed payload is the sole source of truth.** The LLM never
  computes, rounds, or converts a number.
- **Secrets are never logged.** The audit log
  (`backend/src/storage/run_store.py`) records verification results,
  generated text, and the numbers used — never API keys, private keys, or
  other secrets.
- **Audit records are append-only.** Each attempt (success or refusal)
  creates a new JSONL line; nothing is ever updated or deleted.

## 10. Production deployment considerations

- **Signing keys**: this application only ever holds a *public* key for
  verification (`PUBLIC_KEY_PATH`). Production private keys must live in
  an HSM/KMS or the trusted signing service — never generate or store them
  here. `backend/scripts/generate_dev_keys.py` and
  `backend/src/signing/sign.py` are for local development and testing only.
- **`MAX_RUN_AGE_SECONDS`**: the shipped default (24h) is a development
  convenience. Set this to your actual business-approved staleness window
  before going live.
- **Audit log**: JSONL (`AUDIT_LOG_PATH`) is fine to start; swap
  `backend/src/storage/run_store.py`'s `append_record`/`read_records` for
  a real database when you need concurrent-writer durability or
  queryability — nothing else in the app needs to change.
- **Glossary review**: `backend/src/glossary/glossary.json` needs a
  native-speaker review pass for Urdu and Arabic terminology before
  production use,
  especially if the product is Shariah-compliant (this glossary currently
  assumes a conventional product — see its `_note` field).
- **Rendering**: this service returns plain text/JSON only. A separate
  rendering layer must handle RTL layout, bidi number embedding, and fonts
  for Urdu/Arabic before anything reaches a PDF — do not pipe raw LLM
  output straight into a renderer.
- **Regulator-specific content**: which fields a disclosure legally must
  cover depends on jurisdiction (SECP, GCC CMA/SAMA, etc.) — the templates
  here are a starting point, not a compliance sign-off.

## 11. Project layout

```
backend/                   the Disclosure Generator itself (Python/FastAPI)
  src/
    models/schemas.py       SignedRun, CalculationPayload, DisclosureRequest/Response
    signing/
      canonical.py           shared canonical byte-serialization (signer + verifier)
      sign.py                 reference signer (belongs conceptually to the calc engine)
      verify.py               signature + freshness + sanity verification
    guard/numeric_guard.py   deterministic, non-LLM numeric traceability check
    glossary/glossary.json  en/ur/ar terminology, single source of truth
    llm/
      client.py               Gemini client (generate_text)
      generate.py              verify -> prompt -> generate -> guard -> retry -> log
      prompts/                 system_prompt.txt + one template per language
    storage/run_store.py    append-only JSONL audit log
    api/
      main.py                 POST /disclosures/generate, GET /health
      dev_tools.py             POST /dev/sign (local testing only, see §5)
  tests/                    pytest suite (offline) + live golden regression
  scripts/
    generate_dev_keys.py         local dev Ed25519 keypair
    generate_golden_fixtures.py  synthetic golden fixture generator
  keys/                     local dev keys only (gitignored)
  data/                     audit.jsonl (gitignored)
  requirements.txt, .env.example, .gitignore

frontend/                  React + Tailwind test console (see §6) -- not
                           part of the Disclosure Generator's own scope
```
