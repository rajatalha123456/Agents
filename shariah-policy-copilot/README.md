# Shariah Policy Copilot

Internal RAG research assistant: retrieves **approved** Shariah rulings/standards,
compares them, flags conflicts, and produces a cited Evidence Pack for a human
Shariah reviewer. **It never issues a fatwa.**

Stack: FastAPI + SQLAlchemy (metadata/audit) + ChromaDB (semantic) + BM25 (keyword)
+ Sentence-Transformers (local embeddings) + Anthropic or Ollama (drafting LLM).

## Folder structure

```
shariah-policy-copilot/
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   ├── app/
│   │   ├── main.py                     # FastAPI app + router registration
│   │   ├── config.py                   # settings + fixed disclaimer/fallback text
│   │   ├── database.py                 # SQLAlchemy engine/session
│   │   ├── models/
│   │   │   ├── document.py             # Document, DocumentChunk  (FR-1..FR-4)
│   │   │   ├── audit.py                # AuditLog                 (FR-19)
│   │   │   └── review.py               # EvidencePack, ReviewStatus (FR-13,17,18)
│   │   ├── schemas/                    # Pydantic request/response models
│   │   ├── ingestion/
│   │   │   ├── loader.py               # PDF/DOCX/TXT -> (page, text)
│   │   │   ├── chunker.py              # section/clause-aware chunking (FR-4)
│   │   │   └── ingest_service.py       # orchestrates parse+chunk+store+embed
│   │   ├── retrieval/
│   │   │   ├── vector_store.py         # ChromaDB semantic search    (FR-7)
│   │   │   ├── keyword_search.py       # BM25 keyword search         (FR-7)
│   │   │   └── hybrid_retriever.py     # merges both + scope filters (FR-8,9)
│   │   ├── agent/
│   │   │   ├── prompts.py              # grounding rules + JSON output contract
│   │   │   ├── llm_client.py           # Anthropic / Gemini / Ollama switch
│   │   │   ├── conflict_detector.py    # deterministic backstop      (FR-14)
│   │   │   ├── evidence_pack_builder.py# assembles + persists pack   (FR-13)
│   │   │   └── copilot_agent.py        # top-level orchestration     (FR-10..15)
│   │   ├── review/review_service.py    # approve/reject               (FR-18)
│   │   ├── audit/audit_service.py      # query + review logging       (FR-19)
│   │   ├── api/                        # documents.py, query.py, review.py routers
│   │   └── utils/security.py           # role header stub — replace with real auth
│   ├── scripts/seed_sample_docs.py     # loads 2 sample docs with a deliberate conflict
│   ├── tests/test_fallback.py
│   └── data/                           # raw_documents/, vector_store/, copilot.db
└── frontend/                            # React + TypeScript + Tailwind UI (Vite)
    ├── src/
    │   ├── api/                        # typed fetch client for the backend
    │   ├── components/                 # IdentityBar, forms, EvidencePackView, ...
    │   ├── context/IdentityContext.tsx # acting-as user id/role (dev stub auth)
    │   └── pages/                      # AskPage, DocumentsPage
    └── .env.example                    # VITE_API_BASE_URL + dev basic-auth creds
```

## Step 1 — Install

```bash
cd shariah-policy-copilot/backend
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

## Step 2 — Configure `.env`

- Fastest to start: leave `LLM_PROVIDER=anthropic` and set `ANTHROPIC_API_KEY`.
- If documents must never leave your network (data-residency, open question #3 in
  the requirements doc): set `LLM_PROVIDER=ollama`, run `ollama pull llama3.1`,
  and make sure `ollama serve` is running.
- Embeddings run locally either way (`sentence-transformers`), so semantic search
  never calls an external API.

## Step 3 — Run the API

```bash
# from shariah-policy-copilot/backend, with venv active
python -m uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive Swagger UI. Every endpoint needs
HTTP Basic auth (`admin`/`admin` — dev stub) **plus** headers `X-User-Id` and
`X-User-Role` (see `app/utils/security.py`; replace all of this before production).

## Step 4 — Seed sample documents (optional, recommended first run)

```bash
python -m scripts.seed_sample_docs
```

This ingests two small sample policies that **deliberately disagree** on a late-
payment charge, so your first query demonstrates conflict flagging end to end.

## Step 5 — Ingest a real document

```bash
curl -X POST http://localhost:8000/documents/upload \
  -u admin:admin \
  -H "X-User-Id: owais" -H "X-User-Role: shariah_officer" \
  -F "file=@/path/to/ruling.pdf" \
  -F "document_name=Ta'widh Policy v1" \
  -F "document_type=policy" \
  -F "version=1.0" \
  -F "approval_status=approved" \
  -F "product_category=Murabaha"
```

## Step 6 — Ask a question

```bash
curl -X POST http://localhost:8000/query/ask \
  -u admin:admin \
  -H "X-User-Id: owais" -H "X-User-Role: shariah_researcher" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "owais", "question": "What is the late payment charge for Murabaha?"}'
```

Response is an `EvidencePackOut`: research_summary, relevant_rulings/standards,
key_evidence_excerpts (cited), comparison_table (flags CONFLICT rows), open_issues,
citations, `conflict_flagged`, the fixed disclaimer, and `review_status` — which
always starts as `human_review_required` (FR-17).

## Step 7 — Reviewer approves/rejects

```bash
curl -X POST http://localhost:8000/review/<evidence_pack_id> \
  -u admin:admin \
  -H "X-User-Id: mufti_ahmad" -H "X-User-Role: shariah_reviewer" \
  -H "Content-Type: application/json" \
  -d '{"approve": true}'
```

Only `X-User-Role: shariah_reviewer` is authorized to call this (FR-18).

## Step 8 — Run tests

```bash
pytest tests/
```

## Step 9 — Run the frontend (optional)

```bash
cd shariah-policy-copilot/frontend
npm install
cp .env.example .env       # points VITE_API_BASE_URL at the backend (default: localhost:8000)
npm run dev                # http://localhost:5173
npm run test               # Vitest + Testing Library component tests
```

React + TypeScript + Tailwind UI with an "Ask" tab (question → cited Evidence Pack,
conflict highlighting, reviewer approve/reject) and a "Documents" tab (list + upload).
The identity bar in the header sets the `X-User-Id`/`X-User-Role` headers used for
every request — switch the role to `shariah_reviewer` to see the approve/reject
buttons on an evidence pack.

## What's already wired to the requirements doc

| Requirement | Where |
|---|---|
| FR-1..FR-4 (ingestion, metadata, chunking) | `app/ingestion/`, `app/models/document.py` |
| FR-5..FR-9 (search, hybrid retrieval, scope/filters) | `app/retrieval/` |
| FR-10..FR-13 (grounded generation, citations, comparison, evidence pack) | `app/agent/` |
| FR-14 (conflict flagging, never silently merged) | `app/agent/conflict_detector.py` |
| FR-15 (no-evidence fallback, never general knowledge) | `app/agent/copilot_agent.py` |
| FR-16..FR-18 (disclaimer, human review workflow, reviewer approval) | `app/config.py`, `app/review/`, `app/models/review.py` |
| FR-19 (audit logging) | `app/audit/` |
| NFR-3 (access control) | `app/utils/security.py` — **stub, replace before prod** |
| NFR-4 (versioning) | `Document.is_current_version` + `supersedes_document_id` |

## What still needs real decisions from you (see doc §12)

1. **Auth**: `app/utils/security.py` is a header-based stub — swap for real
   SSO/LDAP/JWT (you've already done LDAP auth work on the EMS project).
2. **Data residency**: switch `LLM_PROVIDER` to `ollama` if docs can't leave the network.
3. **Postgres**: swap `DATABASE_URL` for Postgres when you move past a single-node
   deployment — the SQLAlchemy models don't need to change.
4. **Confidentiality-level enforcement**: `confidentiality_level` is stored on
   every document but not yet used to filter results per-user role — wire that
   into `hybrid_retriever._candidate_documents` once your role model is final.
