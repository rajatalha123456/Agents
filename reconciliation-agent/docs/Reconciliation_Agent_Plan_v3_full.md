# Reconciliation Agent — Build Plan v3

**Version:** 3.0
**Supersedes:** Reconciliation Copilot Plan v2.0 (5 September 2026)
**Document type:** Product decision record, architecture specification, rule-pack contract, build plan
**Status:** Implementation-ready baseline
**Product positioning:** Standalone, domain-agnostic reconciliation agent. Domain behaviour pluggable rule packs se aata hai. Amanah Pool OS / Mizan pehla domain pack hoga, core ka hissa nahi.

---

## 0. v2 se kya badla

| Area | v2 | v3 | Wajah |
| --- | --- | --- | --- |
| Product shape | Copilot — human ek exception kholta hai, phir `analyze` dabata hai | **Agent** — scheduled runs, poori queue khud triage karta hai, proposals tayyar rakhta hai | "Agent banana hai" ka faisla; orchestration aur cost model dono is par depend karte hain |
| Domain | Generic, lekin extension ka koi rasta nahi | Generic **core** + **pluggable rule packs** | Standalone bhi chahiye, Mizan bhi — bina do codebase ke |
| Posting model | Sirf external action reference | **Draft journal (internal)** + external action reference, dono | Standalone customers dono tarah ke hain: kuch ka GL bahar hai, kuch ka andar |
| Break taxonomy | 9 flat exception categories | **48 core break codes, 6 families**, registry ke through data-driven | Routing, tolerance aur auto-match policy break code par hang karti hai |
| Auto-match | "Exact rule pass → Matched" | **Confidence bands + false-match budget + circuit breaker** | Financial recon mein false match sabse mehnga error hai |
| Close cycle | Nahi tha | **Period close, certification, roll-forward** | Standalone recon product isi par bikta hai |
| Bank formats | CSV/Excel | + **MT940, CAMT.053, BAI2, ISO 20022** | Banking ki default zubaan |
| Multi-tenancy | Zikr tha, faisla nahi | **Shared schema + RLS** (decision recorded) | Baad mein migrate karna mehnga hai |
| Guardrail | FR-021 requirement | FR-021 + **CI architecture test** jo build fail karta hai | Requirement jo test nahi hoti wo requirement nahi hoti |

v2 ki jo cheezein waise ki waise carry ho rahi hain: rule-first architecture, do data paths (SQL = facts, RAG = knowledge), structured JSON output with backend ID validation, decimal money, raw+normalized dual storage, idempotent imports, immutable audit.

---

## 1. Product decision: Agent, Copilot nahi

Ye document ka sabse important faisla hai. Baaqi sab isi se derive hota hai.

### 1.1 Farq kya hai

| | Copilot (v2) | Agent (v3) |
| --- | --- | --- |
| Trigger | Human `analyze` dabata hai | Schedule, event, ya threshold |
| Scope | Ek case | Poora break queue |
| Timing | Real-time, human wait karta hai | Batch, human ke aane se pehle |
| Human ka kaam | Poochna, phir parhna | Sirf review aur decide |
| Cost profile | Per-click, unpredictable | Per-run, budgeted aur cappable |
| Failure mode | User ko jawab nahi milta | Queue stale ho jati hai — degraded, blocked nahi |

### 1.2 Autonomy levels

Agent ke paas 4 levels hain. Level per universe, per tenant configure hota hai — global nahi.

| Level | Naam | Agent kya karta hai | Default |
| --- | --- | --- | --- |
| A0 | Observe | Sirf run karta hai, matching karta hai, kuch propose nahi karta | Onboarding ke pehle 2 hafte |
| A1 | Propose on demand | Human ke kehne par ek case analyze karta hai (v2 wala behaviour) | Fallback jab schedule off ho |
| A2 | **Propose on schedule** | Har run ke baad poori queue triage karta hai, ranked proposals tayyar karta hai | **Production default** |
| A3 | Auto-match | A2 + whitelisted universes mein high-confidence deterministic matches khud confirm karta hai | Opt-in, per universe, after back-test |

**A4 (auto-post) ka wajood hi nahi hai.** Ye configuration option nahi hai — code mein aisa koi path nahi.

### 1.3 Agent run loop

```
SENSE      →  PLAN       →  ACT        →  PROPOSE    →  PARK
new run       rank queue     read tools    draft         human queue
new data      by risk        gather        proposal      mein daal
ageing        × value        evidence      + evidence    do
threshold     × age          (budgeted)    + confidence
```

Har phase par budget lagta hai (§11.4). Budget khatam hone par agent rukta hai aur jo bacha hai use `NOT_ANALYSED` mark karta hai — kabhi bhi adhoora ya guessed proposal nahi deta.

### 1.4 Queue prioritisation formula

```
priority = w1·log10(1 + |amount|)
         + w2·break_type.risk_weight
         + w3·age_days
         + w4·close_deadline_pressure
         + w5·(1 if repeat_counterparty_break else 0)
```

Weights configuration se aate hain (§32), hardcode nahi. Rationale har case par store hota hai taake agent ka triage order bhi auditable ho.

---

## 2. Architecture principle: Core + Rule Packs

### 2.1 Split

```
┌─────────────────────────────────────────────────────────┐
│  CORE ENGINE  (domain-agnostic, ek codebase)            │
│                                                          │
│  ingestion · normalization · matching · tolerance        │
│  break lifecycle · maker-checker · approval routing      │
│  agent runtime · tool registry · RAG · audit             │
│  close & certification · dashboard · API                 │
└─────────────────────────────────────────────────────────┘
                          ▲
                          │ pack contract (§5)
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   ┌────┴────┐      ┌─────┴─────┐    ┌──────┴──────┐
   │  core   │      │  islamic  │    │  insurance  │
   │  pack   │      │  finance  │    │    pack     │
   │(default)│      │   pack    │    │             │
   └─────────┘      └───────────┘    └─────────────┘
                     = Mizan / Amanah
```

### 2.2 Non-negotiable rule

> **Core mein kisi domain ka naam nahi aayega.** Na `pool`, na `mudarabah`, na `policy_premium`, na `claim`. Agar core code mein domain lafz likhna par raha hai, matlab extension point missing hai — extension point banao, domain lafz mat likho.

Ye rule CI mein enforce hoga: ek lint test jo core packages mein banned-vocabulary list scan karta hai.

### 2.3 Kya core mein hai aur kya pack mein

| Concern | Core | Pack |
| --- | --- | --- |
| Universe **mechanism** (do sides, keys, tolerance apply karna) | ✅ | |
| Universe **definitions** (kaun si side kis se milegi) | | ✅ |
| Break lifecycle state machine | ✅ | |
| Break **type registry** (codes, risk weights, sensitivity) | mechanism | ✅ definitions |
| Matching algorithms (exact, fuzzy, group, scoring) | ✅ | |
| Tolerance **defaults** aur field weights | | ✅ |
| Approval routing **engine** | ✅ | |
| Routing **rules** (break family → role) | | ✅ |
| Roles ka concept | ✅ | |
| Role **names** aur segregation matrix | | ✅ |
| RAG pipeline | ✅ | |
| Knowledge corpus aur namespace | | ✅ |
| Journal draft **mechanism** | ✅ | |
| Journal **templates** aur account mapping | | ✅ |
| Custom validators/enrichers **hook** | ✅ | |
| Validator/enricher **implementations** | | ✅ |
| Dashboard framework aur widgets | ✅ | |
| Dashboard **labels, KPIs, terminology** | | ✅ |

### 2.4 Extension points — core mein din 1 se hone chahiye

Agar ye 10 cheezein core v1 mein na hui, to Mizan pack ke waqt core rewrite karna paregi. Yehi is document ka asal maqsad hai.

| # | Extension point | Kya enable karta hai |
| --- | --- | --- |
| EP-01 | `dimensions` JSONB canonical record par + indexable dimension registry | Mizan ka `pool_id`, `contract_version`, `allocation_run_id` bina schema change ke |
| EP-02 | Break type registry as **data** (table, not enum) | Pack apne break codes add kare |
| EP-03 | `is_sensitive` flag har break type par | Sensitive breaks kabhi auto-match na hon |
| EP-04 | Routing rules table: `(break_family, amount_band, dimension_filter) → role` | Shariah breaks Shariah Secretariat ko jayen, finance manager ko nahi |
| EP-05 | Validator/enricher plugin hook, normalization ke baad chalta hai | Pack-specific data checks |
| EP-06 | Knowledge corpus namespacing per pack | Islamic finance policies generic policies se alag rahen |
| EP-07 | Journal draft template registry | Pack apne debit/credit templates de |
| EP-08 | Universe definitions as **data** | Naye universes bina deploy ke |
| EP-09 | Outbound event bus | Mizan / allocation agent ko handoff |
| EP-10 | Evidence type registry | Pack apni evidence kinds define kare (fatwa ref, disbursement proof) |

---

## 3. Scope

### 3.1 In scope (core, standalone)

- Read-only ingestion: CSV, Excel, MT940, CAMT.053, BAI2, ISO 20022 pain/camt, aur read-only REST/DB connectors.
- Column mapping studio with AI-assisted suggestion aur saved templates.
- Validation, cleaning, normalization, quarantine.
- Deterministic exact matching.
- Tolerance-based matching (date, amount, reference, fee).
- Group matching: 1:1, 1:N, N:1, N:M.
- Duplicate aur missing-record detection.
- Candidate scoring aur learned re-ranking.
- Break creation, classification, ageing, assignment.
- Agent runtime: scheduled runs, queue triage, evidence gathering, proposal drafting.
- RAG knowledge retrieval (policies, SOPs, approved precedent).
- Human review: approve / reject / return / escalate.
- Maker-checker aur approval limits.
- Draft journal generation (internal subledger) **aur** external action reference (external GL).
- Period close, certification aur roll-forward.
- Dashboard, reports, audit export.
- Rule pack install, version aur activate.

### 3.2 Out of scope — permanent

Agent ko ye permissions **kabhi nahi** milengi. Ye configuration nahi hai, ye architecture hai.

- Financial entry post karna (kisi bhi system mein, internal subledger samet).
- Write-off execute karna.
- Original source transaction edit ya delete karna.
- Payment release ya transfer.
- Human approval bypass karna.
- Apni autonomy level khud badalna.
- Apna budget khud barhana.
- Source-system credentials access ya expose karna.

### 3.3 Out of scope — v1 ke liye (baad mein aa sakta hai)

- Intercompany matching aur elimination.
- Full accounting close ke saath flux analysis.
- Cash forecasting.
- Direct write-back to source ERP (approval ke baad bhi — v1 mein human hi karega).

---

## 4. Core domain model

Ye schema **pack-neutral** hai. Har domain-specific cheez `dimensions` ya registry tables se aati hai.

### 4.1 Canonical record

```
canonical_record
├── id                    uuid, pk
├── tenant_id             uuid, RLS key
├── run_id                uuid
├── side                  enum: SOURCE_A | SOURCE_B  (universe define karta hai)
├── connector_id          uuid
├── external_ref          text        -- source system ka ID
├── posted_date           date
├── value_date            date
├── booking_ts            timestamptz nullable
├── amount                numeric(28,8)   -- NEVER float
├── direction             enum: DR | CR
├── currency              char(3)
├── fx_rate               numeric(28,12) nullable
├── base_amount           numeric(28,8)   -- tenant base ccy mein
├── account_ref           text
├── counterparty_raw      text
├── counterparty_id       uuid nullable   -- entity resolution ke baad
├── reference_raw         text
├── reference_canonical   text            -- normalized, indexed
├── description_raw       text
├── description_clean     text
├── dimensions            jsonb           -- EP-01 : pack ka khel yahan
├── raw_payload           jsonb           -- original, kabhi mutate nahi
├── row_fingerprint       text            -- duplicate detection
├── status                enum (§4.4)
├── quarantine_reason     text nullable
└── created_at            timestamptz
```

`dimensions` par GIN index. Dimension registry batata hai kaun si keys indexable hain aur queryable:

```
dimension_registry
├── tenant_id, pack_id
├── key            e.g. "pool_id"
├── label          e.g. "Pool"
├── data_type      string | number | date | uuid
├── is_indexed     bool
├── is_filterable  bool     -- dashboard filters mein aayegi
└── is_isolating   bool     -- true ho to cross-dimension match block hoga
```

`is_isolating` sabse ahem hai. Mizan pack `pool_id` ko `is_isolating = true` set karega — matlab do alag pools ke records aapas mein match hi nahi kar sakte, aur agar cash aisa move karta dikhe to wo apne aap ek break banega. Core ko "pool" ka matlab nahi pata; core sirf itna janta hai ke isolating dimension cross nahi karni.

### 4.2 Baaqi core entities

| Entity | Purpose | Ahem fields |
| --- | --- | --- |
| `tenant` | Organization | id, base_currency, timezone, close_calendar_id, active_packs[] |
| `connector` | Ek data source | type, format, schedule, credentials_ref (read-only), mapping_template_id |
| `mapping_template` | Column mapping config | source_signature, field_map, transforms, version |
| `import_batch` | Ek file/pull | checksum, idempotency_key, row_counts, control_totals, status |
| `universe` | Do sides ka reconciliation definition | side_a_filter, side_b_filter, match_keys, tolerance_profile_id, autonomy_level |
| `recon_run` | Ek execution | universe_id, period, started_at, stats, engine_version, pack_versions |
| `match_group` | Matched set | cardinality, confidence, rule_id, rule_version, decided_by, decided_at |
| `match_member` | Group ka member | match_group_id, record_id, role (primary/offset/fee) |
| `break_case` | Ek unresolved item | break_type_code, severity, amount, age_days, owner, status, universe_id, dimensions |
| `break_type` | **Registry** (EP-02) | code, family, label, description, risk_weight, is_sensitive, pack_id |
| `proposal` | Agent ki recommendation | break_id, kind, payload, confidence, evidence[], model_version, prompt_version |
| `evidence_item` | Proposal ka support | kind, ref_type, ref_id, snippet, retrieval_score |
| `decision` | Human ka faisla | actor, action, reason, timestamp, prior_status, new_status |
| `journal_draft` | Internal subledger draft | lines[], template_id, status (DRAFT/SUBMITTED/APPROVED/POSTED), posted_by |
| `external_action_ref` | Bahar ke system mein hui action | system, reference_id, performed_by, verified_by, evidence_ref |
| `tolerance_profile` | Tolerance ka set | field rules, priority, effective_from, approved_by |
| `routing_rule` | Approval routing (EP-04) | break_family, amount_band, dimension_filter, required_role, escalation_role |
| `knowledge_document` | RAG source | title, type, version, effective_from, effective_to, status, pack_id, access_level |
| `document_chunk` | RAG unit | doc_id, text, page, section, metadata, embedding, embedding_model_version |
| `retrieval_trace` | Har retrieval | case_id, query, filters, returned_ids, scores |
| `agent_run` | Ek agent execution | run_id, autonomy_level, budget_used, cases_analysed, cases_skipped, outcome |
| `audit_event` | Immutable log | actor, event_type, before, after, ts, hash_prev |
| `close_period` | Period close | period, status, deadline, certifier, certified_at |
| `account_reconciliation` | Account-level close item | account_ref, period, opening, movement, closing, explained, unexplained, sign_off |

### 4.3 Do alag lifecycles — v2 ki ghalti

v2 mein record status aur case status ek hi diagram mein mix the. Yahan alag hain.

**Record lifecycle:**

```
INGESTED → NORMALIZED → { MATCHED | UNMATCHED | QUARANTINED }
MATCHED → UNMATCHED   (agar match reverse ho jaye)
```

**Case lifecycle:**

```
                    ┌──────────────────────────────────┐
                    ▼                                  │
OPEN → TRIAGED → PROPOSED → UNDER_REVIEW → { APPROVED | REJECTED | RETURNED }
                                                │            │          │
                                                │            └──────────┘
                                                │                 ▼
                                                │              TRIAGED
                                                ▼
                                          ACTION_PENDING → RESOLVED → CLOSED
                                                                        │
                                          REOPENED ◄────────────────────┘
                                             │        (separate permission
                                             ▼         + mandatory reason)
                                          TRIAGED
```

Alag se: `CARRIED_FORWARD` — jab period close ho jaye aur case abhi unresolved ho (§16).

### 4.4 Integrity constraints

- Ek record ek waqt mein ek hi active `match_group` mein ho sakta hai.
- `match_group` ka net amount tolerance ke andar zero hona chahiye (ya universe ki defined expectation ke barabar).
- Auto-matched group par `decided_by = 'AGENT'` aur `autonomy_level = 'A3'` dono record hon.
- Koi bhi `canonical_record.raw_payload` posting ke baad mutate nahi hoga.
- `audit_event` mein delete ya update nahi — sirf insert. Har event previous event ka hash carry karta hai (tamper-evident chain).
- Isolating dimension cross karne wala match group create hi nahi ho sakta (DB constraint, application check nahi).
- Money hamesha `numeric`, kabhi `float`/`double` nahi.

---

## 5. Rule pack contract

Ye contract v3 ka core innovation hai. Pack ek versioned bundle hai jo core ke andar install hota hai.

### 5.1 Manifest

```yaml
pack:
  id: islamic-finance
  name: Islamic Finance / Pool Management
  version: 1.0.0
  engine_compat: ">=1.0.0 <2.0.0"
  vendor: Novu Labs
  description: Shariah-compliant pool reconciliation rules

dimensions:
  - key: pool_id
    label: Pool
    data_type: uuid
    is_indexed: true
    is_filterable: true
    is_isolating: true          # cross-pool match blocked
  - key: contract_version
    label: Contract version
    data_type: string
    is_indexed: true
  - key: allocation_run_id
    label: Allocation run
    data_type: uuid
    is_indexed: true

roles:
  - code: SHARIAH_SECRETARIAT
    label: Shariah Secretariat
    can_approve: [SHA]
    cannot: [POST, WRITE_OFF]
  - code: FINANCE_CHECKER
    label: Finance Checker
    can_approve: [TIM, AMT, REF, DUP, CLS, DAT]

universes:
  - code: U-POOL-CASH
    label: Pool cash vs bank
    side_a: { connector_type: BANK_STATEMENT }
    side_b: { connector_type: SUBLEDGER, filter: "account_type = 'POOL_CASH'" }
    match_keys: [amount, value_date, reference_canonical]
    tolerance_profile: standard-bank
    require_dimension: [pool_id]
    autonomy_level: A2

break_types:
  - code: SHA-01
    family: SHA
    label: Interest or markup credit on placement account
    risk_weight: 10
    is_sensitive: true
    default_route: SHARIAH_SECRETARIAT
    guidance_doc: POL-PURIFICATION-01

tolerances:
  - profile: standard-bank
    rules:
      - field: value_date
        type: day_window
        value: 2
      - field: amount
        type: absolute_or_percent
        absolute: 5.00
        percent: 0.001
        currency: PKR

routing:
  - when: { family: SHA }
    require_role: SHARIAH_SECRETARIAT
    allow_auto_match: false           # override, hamesha
  - when: { family: AMT, amount_gte: 1000000 }
    require_role: FINANCE_CHECKER
    escalate_to: HEAD_OF_FINANCE

knowledge:
  namespace: islamic-finance
  document_types: [FATWA, SHARIAH_POLICY, SOP, PRECEDENT]
  precedent_rank_below_policy: true

journal_templates:
  - code: JT-PURIFICATION
    label: Route non-permissible income to charity payable
    lines:
      - { side: DR, account_role: NON_PERMISSIBLE_CLEARING }
      - { side: CR, account_role: CHARITY_PAYABLE }
    requires_role: SHARIAH_SECRETARIAT

validators:
  - id: asset-assignment-check
    hook: post_normalization
    impl: islamic_finance.validators.assert_asset_assigned_at_value_date

events:
  emit:
    - allocation.anomaly.suspected     # Mizan ko handoff
```

### 5.2 Pack lifecycle

| Stage | Kya hota hai |
| --- | --- |
| Upload | Manifest schema-validate hota hai; `engine_compat` check hoti hai |
| Dry-run | Pack ki rules pichlay 3 mahine ke data par shadow chalti hain; diff report banti hai |
| Approve | Tenant admin + business owner sign-off (maker-checker) |
| Activate | Effective-dated. Purani pack version `SUPERSEDED` hoti hai, delete nahi |
| Rollback | Pichli version par wapas; jo cases nayi version se bane wo `PACK_ROLLBACK` flag ke saath rehte hain |

### 5.3 Pack conflict rules

- Do packs ek hi break code define nahi kar sakte. Code namespace prefix se unique hota hai.
- Dimension key collision par install fail hota hai.
- `allow_auto_match: false` hamesha jeetta hai, chahe koi doosri rule true kare. Restriction hamesha permission se upar hai.
- Core pack (`core@1.x`) hamesha installed rehta hai aur uninstall nahi ho sakta.

---

## 6. Ingestion aur format support

### 6.1 Supported formats

| Format | Priority | Notes |
| --- | --- | --- |
| CSV / TSV | Must (v1) | Delimiter, encoding, header detection auto |
| Excel (xlsx/xls) | Must (v1) | Multi-sheet, merged header handling |
| **MT940 / MT942** | Must (v1) | SWIFT statement; :61:/:86: field parsing, structured narrative sub-fields |
| **CAMT.053 / .052 / .054** | Must (v1) | ISO 20022 XML bank statement |
| **BAI2** | Should (v2) | US banks |
| pain.002 | Should (v2) | Payment status report — return/reject reasons |
| Read-only REST | Must (v1) | Cursor pagination, incremental by watermark |
| Read-only DB view | Should | Direct view access, no write grant |

MT940 aur CAMT.053 v1 mein hone chahiye. Inke baghair banking customer ke saath conversation shuru hi nahi hoti.

### 6.2 Import guarantees

- Har import ka `idempotency_key = hash(tenant, connector, file_checksum, period)`. Same file dobara upload ho to naya batch nahi banta.
- Control totals (row count, debit sum, credit sum) file se extract ya calculate hote hain aur reconcile hote hain — mismatch par import `HELD` hota hai, silently accept nahi.
- Raw file object storage mein encrypted preserve hoti hai, retention policy tak.
- Invalid rows `quarantine` table mein jate hain with reason. **Silently drop kabhi nahi.**
- Partial import allowed nahi — ya poora batch commit hoga ya poora reject.

### 6.3 Connector security

- Credentials secrets vault mein, DB mein nahi.
- Connector grant read-only verify hota hai onboarding par (write attempt test chalta hai aur fail hona chahiye).
- Har connector call ka audit event.

---

## 7. Normalization pipeline

```
raw → schema map → validate → clean → normalize → fingerprint → entity resolve → features → canonical
```

### 7.1 Normalization rules

| Field | Rule |
| --- | --- |
| Date | Timezone-aware parse; `posted_date` aur `value_date` kabhi ek doosre par overwrite nahi |
| Amount | `numeric(28,8)`; sign se `direction` derive hota hai; original sign convention preserve |
| Currency | ISO 4217 validate; unknown code = quarantine |
| Reference | `reference_canonical = upper(strip_non_alnum(reference_raw))`; raw preserve |
| Counterparty | Legal suffix strip (LTD, PVT, LLC) **configurable list se**; raw preserve |
| Description | Control chars strip, whitespace collapse; raw preserve |
| Nulls | `NULL`, `''`, aur `'UNKNOWN'` teeno alag represent hote hain |

### 7.2 Fingerprint

```
row_fingerprint = sha256(
    account_ref || amount || currency || value_date ||
    reference_canonical || counterparty_id || direction
)
```

Duplicate fingerprint = flag, **automatic delete nahi**. Human decide karega.

### 7.3 Derived matching features

`amount_delta`, `base_amount_delta`, `date_delta_days`, `value_date_delta_days`, `reference_similarity` (Jaro-Winkler + token set), `reference_contains`, `counterparty_similarity`, `description_token_overlap`, `currency_match`, `account_match`, `direction_opposite`, `group_amount_delta`, `historical_pair_frequency`, `channel_match`.

---

## 8. Matching engine

Rule-first. LLM matching engine ka hissa **nahi** hai.

### 8.1 Layers

| Layer | Naam | Method | Deterministic? |
| --- | --- | --- | --- |
| L1 | Exact | Sab match keys exact | Haan |
| L2 | Tolerance | Approved tolerance profile ke andar | Haan |
| L3 | Group | 1:N, N:1, N:M subset-sum with pruning | Haan |
| L4 | Candidate scoring | Blocking + weighted feature score | Haan (seeded) |
| L5 | Learned re-ranker | Gradient-boosted model on historical dispositions | Nahi — isi liye sirf ranking, decision nahi |

**L5 kabhi bhi akela match confirm nahi karta.** Wo sirf L4 ke candidates ko re-order karta hai. Confirm karne ka faisla L1/L2/L3 rule ya human karta hai.

### 8.2 Blocking strategy

Full cross-join se bachne ke liye candidates blocking keys se aate hain:
- `(currency, amount rounded to 2dp)` — sabse strong
- `(currency, value_date ± window)`
- `(reference_canonical prefix 6)`
- `(counterparty_id, month)`

Har block ka size cap hota hai. Cap cross ho to break type `DAT-07 Candidate explosion` banta hai aur human ko batata hai ke matching keys tight karni hain.

### 8.3 Group matching guardrails

Subset-sum NP-hard hai. Bina control ke ye system ko mar dega.

- Max group size configurable, default 8.
- Max candidate pool per group attempt: 200.
- Time budget per group: 500ms.
- Group match ko hamesha L1/L2 se **kam** confidence milti hai — kyunki accidental sum matching real hoti hai.
- Group match sensitive break types par kabhi auto nahi.

---

## 9. Confidence, bands aur false-match budget

Ye section v2 ka sabse bara gap bharta hai.

### 9.1 Confidence calibration

Raw similarity score probability nahi hota. Do qadam:

1. **Score:** L4/L5 weighted score, 0–1.
2. **Calibration:** Isotonic regression jo historical labelled dispositions par fit hoti hai, per universe. Output = calibrated probability ke ye match sahi hai.

Calibration monthly re-fit hoti hai aur uska reliability diagram dashboard par dikhta hai (§21). Agar calibration error (ECE) threshold cross kare, auto-match band suspend ho jata hai.

### 9.2 Bands

| Band | Calibrated p | Agent kya karta hai | Human ka kaam |
| --- | --- | --- | --- |
| AUTO | ≥ 0.98 **aur** L1/L2 deterministic **aur** universe A3 par **aur** break type non-sensitive | Match confirm karta hai | Sample review (§9.4) |
| SUGGEST | 0.85 – 0.98 | Ranked proposal + evidence | One-click accept/reject |
| INVESTIGATE | 0.60 – 0.85 | Evidence gather karta hai, top candidates dikhata hai, **koi ek recommend nahi karta** | Khud decide kare |
| NONE | < 0.60 | Sirf facts aur context | Poori investigation |

**Override:** koi bhi break type jiska `is_sensitive = true` hai, wo hamesha SUGGEST se upar nahi jata — chahe p = 0.999 ho.

### 9.3 False-match budget

| Metric | Target | Breach par |
| --- | --- | --- |
| Auto-match false rate | ≤ 1 per 10,000 | Auto-match circuit breaker trip, universe A2 par gir jata hai |
| Suggest acceptance rate | ≥ 80% | Model review trigger |
| Suggest false-accept (post-hoc detected) | ≤ 0.5% | Band threshold raise |
| Calibration ECE | ≤ 0.05 | Auto-match suspend |

Circuit breaker **automatic** hai. Human ko reset karna parta hai reason ke saath.

### 9.4 Auto-match assurance sampling

Auto-matched items ka mtlab ye nahi ke wo review se bahar hain. Har period:
- Random 2% sample
- Plus 100% of top-decile-by-value auto-matches
- Plus stratified sample per universe

Reviewer disagreement = false-match counter increment. Ye v2 ka `Matched → Closed` shortcut theek karta hai.

---

## 10. Break taxonomy — 48 core codes

Registry table mein data ke taur par, enum nahi (EP-02). Pack apne codes add karta hai.

### TIM — Timing aur cut-off

| Code | Break | Risk |
| --- | --- | --- |
| TIM-01 | Credit in transit — value date cut-off ke baad | 2 |
| TIM-02 | Debit in transit / uncleared payment | 2 |
| TIM-03 | Source system EOD import snapshot ke baad posted | 3 |
| TIM-04 | Calendar mismatch (holiday/weekend) do sides ke darmiyan | 2 |
| TIM-05 | Backdated value date sealed period cross kar raha hai | 8 |
| TIM-06 | Accrual dono sides par alag period mein recognised | 5 |
| TIM-07 | Payment file released, settlement confirmation missing | 6 |
| TIM-08 | Timezone offset se day-shift cross-border feed par | 4 |

### AMT — Amount, FX aur rounding

| Code | Break | Risk |
| --- | --- | --- |
| AMT-01 | Amount mismatch tolerance ke andar | 1 |
| AMT-02 | Amount mismatch tolerance se bahar | 6 |
| AMT-03 | Rounding residual designated account mein route nahi hua | 4 |
| AMT-04 | FX rate difference feed aur base currency ke darmiyan | 4 |
| AMT-05 | Bank charge gross receipt se net ho gaya | 3 |
| AMT-06 | Partial settlement ek ledger entry ke against | 4 |
| AMT-07 | Aggregated credit kai ledger lines ke against (N:1) | 3 |
| AMT-08 | Sign/direction reversal — debit credit ke taur par booked | 7 |

### REF — Reference aur identity

| Code | Break | Risk |
| --- | --- | --- |
| REF-01 | Structured reference missing, sirf free-text narrative | 3 |
| REF-02 | Counterparty reference invalid ya unregistered | 5 |
| REF-03 | Reference kisi doosre account/entity se belong karta hai | 7 |
| REF-04 | Mandate / IBAN master data se match nahi karta | 6 |
| REF-05 | Reference payment rail ne truncate kar diya | 3 |
| REF-06 | Document/invoice reference source system mein maujood nahi | 5 |
| REF-07 | Journal batch reference GL side par missing | 4 |
| REF-08 | Entity resolution ambiguous — ek se zyada master match | 4 |

### DUP — Duplication aur omission

| Code | Break | Risk |
| --- | --- | --- |
| DUP-01 | Duplicate line same side par (fingerprint match) | 6 |
| DUP-02 | Duplicate from re-run import | 5 |
| DUP-03 | Side A par movement hai, side B par entry nahi | 6 |
| DUP-04 | Side B par entry hai, side A par movement nahi | 6 |
| DUP-05 | Returned/re-presented collection dobara collect hua | 7 |
| DUP-06 | File dobara process hua — control total match, checksum alag | 6 |
| DUP-07 | Reversal posted, original maujood nahi | 7 |
| DUP-08 | Original do baar reverse hua | 8 |

### CLS — Classification aur GL

| Code | Break | Risk |
| --- | --- | --- |
| CLS-01 | Account mapping missing | 5 |
| CLS-02 | Suspense/clearing mein posted, koi disposition nahi | 6 |
| CLS-03 | Expense approved taxonomy mein nahi | 5 |
| CLS-04 | Income galat account mein mapped | 5 |
| CLS-05 | Control account variance — subledger vs GL | 8 |
| CLS-06 | Reserve movement bina approved appropriation reference | 7 |
| CLS-07 | Provision/write-off bina linked approval | 8 |
| CLS-08 | Suspense ageing threshold cross kar gayi | 6 |

### DAT — Data quality aur ingestion

| Code | Break | Risk |
| --- | --- | --- |
| DAT-01 | Required field missing | 4 |
| DAT-02 | Unparseable date | 4 |
| DAT-03 | Invalid ya unknown currency code | 5 |
| DAT-04 | Control total mismatch file aur parsed rows ke darmiyan | 8 |
| DAT-05 | Encoding / character corruption detected | 3 |
| DAT-06 | Connector feed expected window mein nahi aayi (missing feed) | 7 |
| DAT-07 | Candidate explosion — blocking key bohat loose hai | 4 |
| DAT-08 | Schema drift — source ne column add/remove/rename kiya | 6 |

**Mizan pack baad mein SHA family (8 codes) add karega** — interest on placement, late-payment charge routing, cross-pool leakage, unassigned asset income, premature Mudarib fee, Qard uplift, purification without proof, distribution before signed run. Core ko inka matlab jannay ki zaroorat nahi; core sirf `is_sensitive: true` dekhta hai aur auto-match block kar deta hai.

---

## 11. Agent runtime

### 11.1 Triggers

| Trigger | Kab |
| --- | --- |
| `run.completed` | Matching run khatam hone par |
| `schedule.cron` | Configurable, default 02:00 tenant timezone |
| `break.aged` | Case ageing threshold cross kare |
| `close.approaching` | Close deadline se N din pehle |
| `user.requested` | Manual (A1 fallback) |

### 11.2 Agent step contract

Har case par agent yeh sequence chalata hai. Sequence fixed hai — agent apna plan khud nahi banata (ye jaan bujh kar hai; predictability > flexibility in financial controls).

```
1. load_case(break_id)                    → facts
2. classify(facts)                        → break_type_code (registry se)
3. gather_candidates(facts, universe)     → SQL, deterministic, capped
4. retrieve_knowledge(break_type, dims)   → RAG, filtered by tenant/effective date
5. retrieve_precedent(break_type, dims)   → approved past cases, ranked below policy
6. build_context(...)                     → minimal, masked, backend-calculated totals
7. draft_proposal(context)                → LLM, structured JSON schema
8. validate(proposal)                     → IDs exist? maths correct? citations resolve?
9. persist(proposal) | fail_to(NOT_ANALYSED)
```

Step 8 fail ho to proposal **save nahi hota**. Ek `analysis_failed` event banta hai reason ke saath. Adhoora proposal dikhana galat proposal dikhane se behtar nahi hai.

### 11.3 Proposal kinds

| Kind | Kya propose karta hai | Human ka action |
| --- | --- | --- |
| `MATCH` | Do ya zyada records ek transaction hain | Accept / reject |
| `SPLIT` | Ek record ko kai ke against partially allocate karo | Accept / adjust |
| `JOURNAL_DRAFT` | Internal subledger mein correcting entry ka draft | Submit → approve → post (teenon human) |
| `EXTERNAL_ACTION` | Bahar ke GL mein kya karna hai + kis authority se | Karo, phir reference record karo |
| `INFO_REQUEST` | Counterparty ya ops se kya poochna hai | Send / edit |
| `CARRY_FORWARD` | Timing item hai, expected clear date ke saath | Accept |
| `ESCALATE` | Is role se upar jana chahiye | Route |
| `SUPPRESS_RULE` | Known benign pattern — rule banao | Approve (mandatory expiry date) |
| `NO_PROPOSAL` | Evidence kaafi nahi | Human investigate kare |

`SUPPRESS_RULE` sabse khatarnaak hai — isi se log breaks chhupate hain. Isliye: mandatory expiry (max 90 din), mandatory reason, checker approval, aur dashboard par "suppressed breaks" ka permanent counter.

### 11.4 Budgets

Har agent run par hard caps:

| Budget | Default | Breach par |
| --- | --- | --- |
| Cases per run | 500 | Baaqi `NOT_ANALYSED`, agle run mein priority upar |
| Tool calls per case | 12 | Case `NOT_ANALYSED` |
| LLM tokens per case | 8,000 in / 1,500 out | Case `NOT_ANALYSED` |
| LLM cost per case | configurable ceiling | Run pause, alert |
| Wall clock per run | 90 min | Graceful stop, state persist |
| LLM-touched breaks | ≤ 12% of queue | Alert — matlab rule engine kamzor hai |

Aakhri metric sabse important hai. Agar 12% se zyada breaks LLM tak pohanch rahe hain, masla model ka nahi, rules ka hai.

---

## 12. Tool registry

Agent ke paas sirf ye tools hain. Har tool permission-scoped hai aur uska har call audit hota hai.

### 12.1 Read tools

| Tool | Purpose |
| --- | --- |
| `get_break_case` | Case facts |
| `get_record` | Ek canonical record + raw payload |
| `find_candidates` | Filtered candidate search (capped, deterministic sort) |
| `get_match_rule_result` | Rule ne kya kaha aur kyun |
| `get_balance` | Account balance at date |
| `get_ageing` | Break ageing profile |
| `search_knowledge` | RAG, tenant + effective-date filtered |
| `get_document_chunk` | Exact cited section |
| `find_precedent` | Approved past cases, similar |
| `get_dimension_value` | Dimension registry lookup |
| `get_counterparty` | Master data |

### 12.2 Draft-only tools

| Tool | Write scope |
| --- | --- |
| `create_proposal` | Sirf `proposal` table, status DRAFT |
| `create_journal_draft` | Sirf `journal_draft` table, status DRAFT |
| `attach_evidence` | Sirf `evidence_item` table |
| `emit_event` | Outbound bus (EP-09), read-only downstream |

### 12.3 Jo tools maujood nahi hain

`post_journal` · `approve` · `write_off` · `release_payment` · `delete_record` · `update_record` · `modify_tolerance` · `change_autonomy` · `install_pack` · `close_period` · `certify`

Ye list documentation nahi hai. Ye ek **test fixture** hai (§29.2).

---

## 13. Guardrails

### 13.1 Architecture guardrail — CI test (FR-021)

```python
# tests/security/test_no_write_tools.py

FORBIDDEN = {
    "post", "write_off", "writeoff", "approve", "certify",
    "release", "pay", "delete", "drop", "truncate",
    "update_record", "modify", "override", "grant",
}

def test_agent_tool_registry_has_no_write_capability():
    for tool in AGENT_TOOL_REGISTRY.all():
        assert tool.write_scope in (None, "DRAFT"), \
            f"{tool.name} has write scope {tool.write_scope}"
        assert not any(f in tool.name.lower() for f in FORBIDDEN), \
            f"{tool.name} matches forbidden verb"

def test_agent_db_role_is_read_plus_draft_only():
    grants = db.query_grants(role="agent_runtime")
    for g in grants:
        if g.privilege in ("INSERT", "UPDATE"):
            assert g.table in DRAFT_TABLES, f"agent can write {g.table}"
        assert g.privilege != "DELETE"
```

Ye test **build fail** karta hai. Koi bhi developer future mein galti se write tool add kare, merge nahi hoga.

### 13.2 Prompt injection

Bank narration attacker-controllable hai — member khud payment reference type karta hai. Design controls:

- Transaction text hamesha **data envelope** ke andar jata hai, kabhi instruction position mein nahi:
  ```
  <untrusted_transaction_data>
  ...narrative...
  </untrusted_transaction_data>
  ```
- System prompt mein explicit: envelope ke andar ka content instruction nahi hai.
- Tool outputs bhi untrusted treat hote hain (RAG chunks samet — kyunki document ingestion bhi ek attack surface hai).
- Output validation content par depend nahi karti — schema aur DB lookup par karti hai. Agar LLM `"approved": true` bhi likh de, wo field schema mein hai hi nahi.
- Injection corpus regression suite mein: ek fixed set of malicious narratives jo har release par chalta hai.

### 13.3 Precedent poisoning

Ek galat approved case index mein ja kar scale par duplicate ho sakta hai.

- Precedent chunks `source_authority: PRECEDENT` label ke saath store hote hain; policy `source_authority: POLICY`.
- Retrieval mein policy hamesha precedent se upar rank hoti hai — conflict par policy jeetti hai aur agent ko conflict explicitly batana parta hai.
- Precedent index mein sirf **closed + certified** cases jate hain, sirf approved nahi.
- Retraction API: koi bhi case index se nikala ja sakta hai, aur uske base par bane proposals flag ho jate hain.
- Quarterly precedent review: sabse zyada retrieve hone wale 50 precedents human review mein jate hain.

### 13.4 Kill switch

| Level | Kya band hota hai | Kaun kar sakta hai |
| --- | --- | --- |
| L1 | Auto-match (A3 → A2) | Tenant admin, ya circuit breaker automatic |
| L2 | LLM proposals (A2 → deterministic templates only) | Tenant admin |
| L3 | Agent poora band (A2 → A0) | Tenant admin |
| L4 | Global, sab tenants | Platform admin |

Har level par **rule-based matching chalta rehta hai**. LLM ya agent ka failure kabhi core reconciliation ko nahi rokta. Ye NFR nahi, architecture hai.

### 13.5 Deterministic fallback

Jab LLM unavailable ho, agent template-based proposals deta hai:

```
Break DUP-03 → template:
  "Side A par {amount} {currency} ka movement {date} ko hai
   ({reference}). Side B par koi corresponding entry nahi mili
   ±{window} din mein. Verify: (1) posting delay,
   (2) galat account, (3) missing entry."
```

Kam useful, lekin sahi. Aur customer ko pata chalta hai ke fallback mode mein hai (UI badge).

---

## 14. Resolution: draft journal + external action

v2 ne sirf external action rakha tha. Standalone product ko dono chahiye kyunki customers do tarah ke hain.

### 14.1 Internal path (platform ka apna subledger hai)

```
Agent  →  JOURNAL_DRAFT proposal  (agent yahan ruk jata hai)
Maker  →  review, edit, submit
Checker → approve  (maker ≠ checker, enforced)
System →  post to subledger
        →  break → RESOLVED
```

Agent ne journal **banaya**, post nahi kiya. Guardrail ye hai ke agent post nahi kar sakta — platform kar sakta hai.

### 14.2 External path (GL bahar hai)

```
Agent  →  EXTERNAL_ACTION proposal (kya karna hai, kis authority se)
Human  →  apne ERP/GL mein action leta hai
Human  →  reference + evidence record karta hai
System →  verify (reference format, amount match, evidence present)
        →  break → RESOLVED
```

Bina valid reference aur evidence ke case close nahi hota.

### 14.3 Write-off

Write-off ek alag hi cheez hai aur isi liye alag treatment:

- Agent write-off ko **request** kar sakta hai, propose nahi. Kind: `ESCALATE` with `reason: WRITE_OFF_CANDIDATE`.
- Write-off approval matrix se jata hai (amount band → role).
- Write-off ke liye hamesha do human chahiye, chahe amount kitna bhi chhota ho.
- Write-off ka apna register hai aur dashboard par apna counter.

---

## 15. Period close aur certification

Ye v2 ka sabse bara functional gap tha. Standalone recon products isi par bikte hain.

### 15.1 Close calendar

```
close_period
├── period            2026-09
├── status            OPEN → SOFT_CLOSE → HARD_CLOSE → CERTIFIED → LOCKED
├── deadline_prep     2026-10-03
├── deadline_review   2026-10-05
├── deadline_certify  2026-10-07
└── tasks[]           account_reconciliation refs
```

### 15.2 Account-level reconciliation

Har reconcilable account ke liye per period:

| Field | Meaning |
| --- | --- |
| `opening_balance` | Pichle period ka closing |
| `movement` | Period ki activity |
| `closing_balance` | Statement/GL ka balance |
| `explained` | Matched + resolved breaks se cover |
| `unexplained` | Baaqi — ye number hi asal reconciliation output hai |
| `supporting_evidence[]` | Statements, schedules, proofs |
| `preparer` / `prepared_at` | Maker |
| `reviewer` / `reviewed_at` | Checker |
| `risk_rating` | High/medium/low — review frequency drive karti hai |

### 15.3 Certification

- Preparer sign-off → Reviewer sign-off → Certifier (controller) sign-off.
- Certification blocked ho agar: unexplained balance > threshold, ya koi high-risk break open ho, ya koi aged item > policy limit ho.
- Certification pack export: har account ka reconciliation, evidence, break log, sign-off trail, aur agent proposals ka disposition summary. Auditor ke liye ek zip.

### 15.4 Agent ka close mein role

- Close deadline ke qareeb queue re-prioritise hoti hai (§1.4 ka `close_deadline_pressure`).
- Agent har account ke liye "close readiness" summary draft karta hai: kya unexplained hai, kyun, kya expected hai.
- Agent certify **nahi** kar sakta. `certify` tool maujood nahi.

---

## 16. Open items roll-forward

Unresolved break agle period mein carry hota hai — naya case nahi banta.

```
Period N close → break OPEN hai
              → status = CARRIED_FORWARD
              → carry_forward_count++
              → original_period preserved
              → age_days continue karta hai (reset nahi hota)
Period N+1    → wahi case, wahi ID, wahi ageing
```

Ye kyun ahem hai: ageing hi wo metric hai jis se auditor aur regulator recon quality judge karte hain. Agar har period naya case bane to ageing hamesha 0 dikhega aur number jhooth bolega.

Roll-forward ke rules:
- `carry_forward_count > 3` → automatic escalation.
- `age_days > 90` → high-risk classification, certification block.
- Carried-forward items ka apna dashboard view hai.

---

## 17. Onboarding aur column mapping

Standalone product mein onboarding hi product hai. Naye customer ki files 1 ghante mein map honi chahiye.

### 17.1 Mapping studio

1. User sample file upload karta hai.
2. System header detect karta hai, data types infer karta hai, first 50 rows preview.
3. **AI-assisted suggestion:** LLM column headers + sample values dekh kar canonical field mapping suggest karta hai. Ye ek safe LLM use case hai — output ek mapping proposal hai jo user confirm karta hai, koi financial faisla nahi.
4. User confirm/adjust karta hai. Har column ka transform bhi (date format, decimal separator, sign convention).
5. Mapping `mapping_template` ke taur par save hoti hai with `source_signature` (header hash) — agli baar same format auto-detect ho jata hai.

### 17.2 Format library

Pre-built templates ship hote hain: bade banks ke MT940 dialects, CAMT.053 variants, common ERP exports (QuickBooks, Xero, NetSuite, SAP, Odoo, Dynamics, Tally). Library community/pack se extend hoti hai.

### 17.3 Schema drift

Source ne column rename ya add kar diya → `DAT-08` break banta hai, import `HELD` hota hai, user ko mapping update karne ko kehta hai. Silently guess **nahi** karta.

---

## 18. Human workflow aur approval

### 18.1 Core roles (pack extend karta hai)

| Role | Kar sakta hai | Nahi kar sakta |
| --- | --- | --- |
| Viewer | Read, comment | Koi decision |
| Preparer / Maker | Investigate, propose, submit, draft journal banana | Apna kaam approve |
| Reviewer / Checker | Approve, reject, return | Apna banaya hua approve |
| Controller / Certifier | Period certify, high-value approve | Post (system posts) |
| Auditor | Read-only sab kuch, evidence export | Koi operational action |
| Admin | Config, rules, connectors, users | Koi financial decision |
| **Agent** | Read, analyze, propose (DRAFT only) | Baaqi sab |

### 18.2 Maker-checker rules

- Proposal banane wala usay approve nahi kar sakta — chahe uske paas checker role bhi ho.
- Agent ka proposal accept karne wala **maker** count hota hai, checker nahi. Matlab agent ke proposal par bhi do human chahiye jab amount limit cross ho.
- Approval limits: `(break_family, amount_band, dimension) → required_role` routing table se (EP-04).
- Closed case reopen: alag permission + mandatory reason + audit event.
- Escalation SLA: har band ka apna, breach par notification aur dashboard flag.

---

## 19. RAG knowledge layer

### 19.1 Do data paths — v2 se carry

| Path | Data | Method | Source of truth? |
| --- | --- | --- | --- |
| Transaction | Amounts, dates, IDs, balances | SQL / API, deterministic | **Haan** |
| Knowledge | Policies, SOPs, precedent | RAG, embeddings + filters | Nahi |

Vector store kabhi bhi financial fact ka source nahi hai. Ye v2 ka BR-001 hai aur bilkul sahi hai.

### 19.2 Chunking aur metadata

Har chunk par mandatory: `tenant_id`, `pack_id`, `document_id`, `version`, `document_type`, `title`, `effective_from`, `effective_to`, `status`, `page_or_section`, `access_level`, `source_authority` (POLICY | SOP | PRECEDENT | GUIDANCE).

### 19.3 Retrieval order

```
1. Hard filter:  tenant + access scope + active version + effective date range
2. Hard filter:  pack namespace (agar break type pack-specific hai)
3. Semantic:     embedding similarity
4. Re-rank:      cross-encoder, optional
5. Authority:    POLICY > SOP > GUIDANCE > PRECEDENT  (hard ordering)
6. Cap:          top-k, default 6 chunks
```

### 19.4 Citation validation

Har citation jo LLM output mein aati hai, backend verify karta hai: chunk ID maujood hai? Retrieval trace mein tha? Effective date case ke date se compatible hai? Ek bhi fail ho to proposal reject hota hai. Ye §11.2 ka step 8 hai.

---

## 20. Multi-tenancy — decision

**Faisla: shared schema + PostgreSQL Row-Level Security, tenant_id har table par.**

| Option | Chuna? | Wajah |
| --- | --- | --- |
| Shared schema + RLS | ✅ | SaaS economics, ek migration, ek connection pool. Standalone product ke liye sahi. |
| Schema per tenant | ❌ | 500 tenants par migration nightmare |
| DB per tenant | Enterprise/on-prem option ke taur par offered | Data residency ya regulator requirement par |

Controls:
- `tenant_id` har table par NOT NULL, RLS policy har table par.
- Application connection tenant-scoped role se banta hai, superuser se nahi.
- pgvector index par bhi tenant filter **query planner level par**, application filter par bharosa nahi.
- Cross-tenant read ka penetration test har release par (v2 ka BR-010 sahi tha).
- Noisy neighbour: matching jobs per-tenant queue + concurrency cap.

---

## 21. Dashboard aur UI

### 21.1 Design direction

BRD §19 ka brand: **premium navy, emerald, gold**. Ye standalone product ke liye bhi rakha ja raha hai — mature, institutional, "trust" wala tone, jo financial control software ko chahiye.

```
Ink navy       #0A1C33   base
Panel          #0F2740   surfaces
Emerald        #1E9E7A   matched, clean, healthy
Gold           #C9A227   pending approval, attention
Crimson        #C0392B   break, breach (sparingly)
Slate          #8FA3B8   secondary text
Parchment      #E8EDF2   primary text
```

Typography: IBM Plex Sans (UI) + IBM Plex Sans Arabic (Urdu/Arabic RTL) + IBM Plex Mono (**sirf amounts aur codes** — tabular figures align hone chahiye, decorative labels ke liye nahi).

Requirements: WCAG 2.2 AA, keyboard-first (recon analysts mouse kam use karte hain), RTL-ready, dark mode default (log ye screen ghanton dekhte hain).

### 21.2 Hero — Reconciliation bridge

Default "big number + sparkline" nahi. Hero ek **tie-out bridge** hai — horizontal waterfall jo dikhata hai:

```
Source A closing  →  matched  →  timing  →  unexplained  →  Source B closing
   1,240,000,000     -1,198M     -38.2M       -3.8M          1,240,000,000
```

Ye reconciliation ka asal artifact hai. Ek nazar mein pata chalta hai ke kitna tie hua aur kya bacha.

### 21.3 Screens

| # | Screen | Kya dikhata hai |
| --- | --- | --- |
| 1 | Control centre | Bridge, close countdown, universe health strip, agent last-run status, breaks by value & age |
| 2 | Universe board | Har universe: matched %, break count, break value, ageing, autonomy level, last run |
| 3 | Run detail | Import stats, control totals, match layer breakdown, rule hit counts, timing |
| 4 | Break queue | Filterable, sortable, bulk-selectable. Value/age/risk columns. Agent proposal badge |
| 5 | Break workspace | Side-by-side records, differences highlighted, proposal card, evidence panel, decision bar |
| 6 | Match canvas | Group matching ke liye — drag records into a group, live net-amount indicator |
| 7 | Proposal review | Agent ka proposal + confidence + calibration context + citations + accept/reject/return |
| 8 | Approval queue | Maker-checker inbox, SLA countdown, escalations |
| 9 | Journal drafts | Draft entries, submit/approve/post pipeline |
| 10 | Suspense & ageing | Ageing buckets **by value not just count**, carried-forward view |
| 11 | Close cockpit | Account reconciliation grid, sign-off status, certification blockers |
| 12 | Certification pack | Evidence bundle preview aur export |
| 13 | Mapping studio | Column mapping, template library, drift alerts |
| 14 | Rule pack manager | Installed packs, versions, dry-run diff, activate/rollback |
| 15 | Agent transparency | Run history, budget usage, tool call log, proposal accept rate, calibration reliability diagram |
| 16 | Model governance | Model/prompt versions, false-match tracker, circuit breaker status, drift |
| 17 | Audit timeline | Immutable event chain per case, exportable |
| 18 | Admin | Users, roles, routing rules, tolerances, connectors, schedules |

### 21.4 Break workspace — sabse important screen

Analyst yahan din guzarta hai. Design rules:

- Do sides side-by-side, matching fields quiet, **differing fields highlighted** (colour + weight, sirf colour nahi — accessibility).
- Proposal card upar, collapsed by default agar confidence SUGGEST band mein hai; INVESTIGATE band mein candidates list dikhti hai bina kisi ko recommend kiye.
- Evidence panel: har citation clickable, exact chunk highlight ke saath khulta hai.
- Decision bar hamesha visible (sticky), keyboard shortcuts: `A` approve, `R` reject, `T` return, `E` escalate, `J` next case.
- "Agent cannot post" ek **permanent badge** hai proposal card par — decoration nahi, ye customer ka primary trust signal hai.
- Fallback mode mein alag badge: "Deterministic mode — LLM unavailable".

### 21.5 Agent transparency screen

Ye screen product ka differentiator hai. Customers ko dikhna chahiye:
- Agent ne kitne case dekhe, kitne skip kiye aur kyun (budget? confidence? sensitivity?)
- Har proposal ka accept rate, per break type
- Calibration reliability diagram — "jab agent 90% kehta hai, kitni baar sahi hota hai?"
- Tool call log per case
- Cost per case
- Circuit breaker history

Jo AI apna hisab nahi de sakta, wo finance mein deploy nahi hota.

---

## 22. API surface

```
# Tenancy & config
POST   /v1/connectors
POST   /v1/mapping-templates
GET    /v1/dimension-registry

# Ingestion
POST   /v1/imports                        (multipart | connector pull)
GET    /v1/imports/{id}
GET    /v1/imports/{id}/quarantine

# Universes & runs
POST   /v1/universes
POST   /v1/runs:execute
GET    /v1/runs/{id}
GET    /v1/runs/{id}/summary

# Matching
GET    /v1/matches
POST   /v1/matches:manual
POST   /v1/matches/{id}:unmatch          (reason mandatory)

# Breaks
GET    /v1/breaks
GET    /v1/breaks/{id}
POST   /v1/breaks/{id}:assign
POST   /v1/breaks/{id}:comment

# Agent
POST   /v1/agent/runs:trigger
GET    /v1/agent/runs
GET    /v1/agent/runs/{id}/trace
POST   /v1/agent/autonomy                 (admin, audited)
POST   /v1/agent:killswitch               (admin, audited)

# Proposals (human decisions)
GET    /v1/breaks/{id}/proposals
POST   /v1/proposals/{id}:accept
POST   /v1/proposals/{id}:reject
POST   /v1/proposals/{id}:return

# Resolution
POST   /v1/journal-drafts
POST   /v1/journal-drafts/{id}:submit
POST   /v1/journal-drafts/{id}:approve    (checker, ≠ maker)
POST   /v1/breaks/{id}/external-action
POST   /v1/breaks/{id}:close

# Close
GET    /v1/close-periods/{period}
POST   /v1/account-reconciliations/{id}:prepare
POST   /v1/account-reconciliations/{id}:review
POST   /v1/close-periods/{period}:certify
GET    /v1/close-periods/{period}/certification-pack

# Knowledge
POST   /v1/knowledge/documents
POST   /v1/knowledge/documents/{id}:index
POST   /v1/knowledge/documents/{id}:retract
POST   /v1/knowledge:search

# Packs
POST   /v1/packs                          (upload)
POST   /v1/packs/{id}:dry-run
POST   /v1/packs/{id}:activate
POST   /v1/packs/{id}:rollback

# Audit
GET    /v1/audit-events
GET    /v1/audit-events:export
```

**API restriction:** agent runtime ke paas is surface ka sirf GET subset + `POST /v1/proposals` (draft) hai. Baaqi sab endpoints human session token maangte hain. Ye gateway level par enforce hota hai, application logic par nahi.

---

## 23. Audit aur evidence

Har audit event mein: actor (human ya `AGENT`), event type, before/after state, timestamp, correlation ID, aur previous event ka hash.

Agent-specific events: `agent.run.started`, `agent.case.analysed`, `agent.case.skipped` (reason ke saath), `agent.tool.called`, `agent.proposal.created`, `agent.proposal.rejected_by_validator`, `agent.budget.exhausted`, `agent.fallback.engaged`.

Evidence bundle export mein: source files (checksums ke saath), import reports, matching rules + versions, break log, agent proposals + dispositions, human decisions + reasons, journal drafts + postings, external action references, sign-off trail. Sab ek manifest ke saath jiska apna hash hai.

---

## 24. Metrics aur model governance

| Category | Metric | Target |
| --- | --- | --- |
| Matching | Auto-match rate | ≥ 85% by volume |
| Matching | False-match rate (auto band) | ≤ 1 : 10,000 |
| Matching | Match precision (suggest band) | ≥ 95% |
| Matching | Match recall vs labelled set | ≥ 90% |
| Agent | Proposal acceptance rate | ≥ 80% |
| Agent | Human override rate | ≤ 20% |
| Agent | Validator rejection rate | ≤ 3% |
| Agent | Citation resolution failure | ≤ 1% |
| Agent | LLM-touched break share | ≤ 12% |
| Agent | Cost per analysed break | ≤ configured ceiling |
| Calibration | Expected calibration error | ≤ 0.05 |
| Operations | Break MTTR | trending down |
| Operations | Aged breaks > 60 days | ≤ 2% of open |
| Operations | Close certification on time | 100% |

Model governance: har model, prompt aur rule version registered hai owner, purpose, validation date aur retirement date ke saath. Version change dry-run ke baghair production mein nahi jata.

---

## 25. LLM unit economics

Standalone SaaS mein ye margin ka sawal hai, technical detail nahi.

| Lever | Design |
| --- | --- |
| Rule coverage | Target: 88%+ breaks bina LLM ke resolve ya classify hon |
| Tiering | Classification aur triage chhote/saste model par; sirf narration aur complex resolution bare model par |
| Caching | Context hash par cache. Same break pattern dobara aaye to cached reasoning re-use ho (with freshness check) |
| Batching | Overnight run mein batch API use ho — real-time pricing nahi |
| Context minimisation | Sirf zaroori fields, masked, backend-calculated totals. Raw batches kabhi nahi |
| Cost ceiling | Per-case aur per-run dono; breach par run pause |
| Metering | Per-tenant cost tracked; pricing model se linked |

Ek practical target: **per analysed break cost < 1% of the average break value's handling cost**. Agar ek break manually 20 minute leta hai, to agent ki cost us 20 minute se bohat kam honi chahiye — warna value proposition nahi banti.

---

## 26. Security aur NFR

### 26.1 Security

- RBAC + attribute-based scoping (dimension-level).
- SSO/MFA privileged roles par mandatory.
- Read-only source connections, verified at onboarding.
- Encryption in transit aur at rest; secrets vault.
- Field-level masking LLM context ke liye.
- File type + malware validation on upload.
- Tenant isolation via RLS, penetration tested per release.
- Audit log append-only, hash-chained.
- Retention policy configurable per tenant/jurisdiction.

### 26.2 Non-functional

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-01 | Interactive API P95 | < 2s |
| NFR-02 | Break queue page load (10k breaks) | < 1.5s |
| NFR-03 | Matching throughput | 1M records / run within 30 min |
| NFR-04 | Agent run window | 500 cases within 90 min |
| NFR-05 | Availability | 99.9% monthly |
| NFR-06 | Degradation | LLM down → deterministic mode; agent down → manual mode; **core recon never blocked** |
| NFR-07 | Reproducibility | Koi bhi run rule/model/prompt/pack version ke saath re-trace ho |
| NFR-08 | RPO / RTO | ≤ 15 min / ≤ 4 hr |
| NFR-09 | Accessibility | WCAG 2.2 AA |
| NFR-10 | Localization | Multi-currency, timezone, EN/UR/AR, RTL |
| NFR-11 | Observability | Job lineage, rule hit rates, retrieval quality, LLM errors, cost |
| NFR-12 | Idempotency | Retry se duplicate batch/case/proposal na bane |

---

## 27. Tech stack

| Layer | Choice | Notes |
| --- | --- | --- |
| Backend | Python 3.12, FastAPI, Pydantic v2 | Typed LLM schemas |
| DB | PostgreSQL 16 + RLS + pgvector | Ek DB, do kaam |
| ORM | SQLAlchemy 2.x + Alembic | |
| Jobs | Celery + Redis | Per-tenant queues |
| Matching | Python + Polars for bulk, RapidFuzz for strings | Pandas se Polars behtar hai is volume par |
| ML re-ranker | LightGBM | Explainable, chhota, CPU par chalta hai |
| Calibration | scikit-learn isotonic | |
| Bank formats | `mt-940` parser + lxml for CAMT | Custom dialect handlers |
| LLM | Provider-neutral adapter (Anthropic default) | Model swap without logic change |
| Frontend | React + Vite + TypeScript | Existing stack se consistent |
| Charts | Visx ya D3 | Bridge chart custom hai |
| Storage | S3-compatible, encrypted | Raw files, evidence |
| Testing | pytest, Playwright, Schemathesis | + custom guardrail suite |

### 27.1 Folder structure

```
backend/
├── core/                      # DOMAIN-AGNOSTIC — banned vocabulary lint yahan chalta hai
│   ├── ingestion/
│   ├── normalization/
│   ├── matching/
│   │   ├── exact.py
│   │   ├── tolerance.py
│   │   ├── grouping.py
│   │   ├── scoring.py
│   │   └── reranker.py
│   ├── breaks/
│   ├── workflow/              # maker-checker, routing, SLA
│   ├── close/                 # period close, certification, roll-forward
│   ├── agent/
│   │   ├── runtime.py
│   │   ├── tools/             # registry — CI test isi ko scan karta hai
│   │   ├── context.py
│   │   ├── validators.py
│   │   └── budgets.py
│   ├── rag/
│   ├── packs/                 # pack loader, manifest schema, conflict resolution
│   ├── audit/
│   └── api/
├── packs/
│   ├── core/                  # default pack — 48 break codes, generic universes
│   ├── islamic_finance/       # Mizan pack — baad mein
│   └── insurance/             # future
├── migrations/
└── tests/
    ├── unit/
    ├── integration/
    ├── security/              # guardrail suite (§29.2)
    ├── packs/
    └── e2e/
```

Business logic API route files mein nahi. Routes request lein, services logic chalayein, repositories DB touch karein.

---

## 28. Delivery roadmap

| Phase | Focus | Exit criteria |
| --- | --- | --- |
| **P0** Foundation | Auth, RLS multi-tenancy, audit chain, pack loader skeleton, CI guardrail suite | Guardrail tests green aur build mein wired |
| **P1** Ingestion | CSV/Excel + MT940 + CAMT.053, mapping studio, validation, quarantine | 3 real bank formats clean import hon |
| **P2** Matching | L1 exact, L2 tolerance, L3 group, break creation, 48 core codes | Historical data par reproducible match rate |
| **P3** Workflow | Break queue, workspace, maker-checker, routing, external action ref | Ek analyst poora case end-to-end kar sake |
| **P4** Close | Account recon, close calendar, certification, roll-forward | Ek poora month-end close cycle complete |
| **P5** Agent (deterministic) | Runtime, scheduler, budgets, tool registry, template proposals | Agent bina LLM ke queue triage kare |
| **P6** Agent (LLM) | RAG, context builder, structured proposals, validators, calibration | Proposal acceptance ≥ 70% on pilot |
| **P7** Scoring & auto-match | L4 scoring, L5 re-ranker, calibration, bands, circuit breaker | False-match budget met on back-test |
| **P8** Dashboard | 18 screens, transparency, model governance | UAT sign-off |
| **P9** Pilot | Ek customer, ek account, limited period | Controlled production adoption |
| **P10** **Mizan pack** | Islamic finance pack (§30) | Amanah Pool OS par pack activate ho, core mein zero change |

**P0 sabse ahem hai.** Agar guardrail suite aur pack loader shuru mein nahi bane, to baad mein retrofit karna practically nahi hota.

Note: P5 (deterministic agent) P6 (LLM agent) se pehle hai — jaan bujh kar. Agent ka runtime, scheduling, budget aur queue triage sab bina LLM ke test hone chahiye. LLM aakhri layer hai, foundation nahi.

---

## 29. Test plan

### 29.1 Functional

| Test | Expected |
| --- | --- |
| Same amount/date/reference | L1 exact match |
| Date within tolerance | L2 match, rule ID recorded |
| Amount outside tolerance | AMT-02 break |
| One bank credit = 3 GL lines | L3 group match, net zero |
| Same file uploaded twice | Idempotency block, no new batch |
| Control total mismatch | Import HELD, DAT-04 break |
| Column renamed in source | DAT-08 break, import HELD |
| Maker approves own proposal | Permission denied |
| Break closed without external ref | Closure blocked |
| Period certified with open high-risk break | Certification blocked |
| Unresolved break at period end | CARRIED_FORWARD, ageing continues |
| Sensitive break type with p=0.999 | SUGGEST band, never AUTO |

### 29.2 Guardrail suite — har build par

| Test | Assertion |
| --- | --- |
| Tool registry scan | Koi write-scoped tool nahi (DRAFT ke ilawa) |
| DB grant scan | Agent role ke paas DELETE nahi, INSERT/UPDATE sirf draft tables par |
| API scope scan | Agent token se non-GET endpoints 403 |
| Banned vocabulary lint | `core/` mein koi domain lafz nahi |
| Prompt injection corpus | 50 malicious narratives — koi bhi tool call ya schema violation trigger na kare |
| Hallucinated ID | LLM output mein fake record ID → proposal rejected |
| Citation resolution | Har citation retrieval trace mein maujood ho |
| Cross-tenant read | Har table par RLS bypass attempt fail ho |
| Autonomy escalation | Agent apna level nahi badal sakta |
| Kill switch | L1–L4 har level par core matching chalti rahe |

### 29.3 AI evaluation

Back-test on historical labelled reconciliations: precision, recall, false-match rate, calibration (reliability diagram + ECE), explanation quality (human rubric), override rate, cost per case, latency.

Har release se pehle back-test dobara chale. Regression = release block.

---

## 30. Mizan pack — baad wala kaam

Ye section batata hai ke standalone se Amanah Pool OS tak jaane mein kya karna hoga. Agar core §2.4 ke extension points ke saath bana, to **core mein ek line bhi nahi badlegi.**

### 30.1 Pack kya add karega

| Item | Detail |
| --- | --- |
| Dimensions | `pool_id` (isolating), `contract_version`, `rule_pack_version`, `allocation_run_id`, `participant_class` |
| Universes | Pool cash ↔ bank; core banking daily balances ↔ imported balances; pool subledger ↔ GL control account; asset income ↔ IncomeEvent; allocation run ↔ journal batch ↔ payout file; circle contributions ↔ PSP file; purification payable ↔ disbursement proof; PER/IRR movement ↔ approved appropriation; suspense ageing; migration reconciliation |
| Break family | **SHA** — 8 codes, sab `is_sensitive: true` |
| Roles | Shariah Secretariat, Shariah Board, Pool Manager, Finance Maker/Checker |
| Routing | SHA family → Shariah Secretariat, `allow_auto_match: false` hardcoded in pack |
| Knowledge | Fatwa register, SBP instructions, AAOIFI GS 1, Shariah policies, approved precedent |
| Journal templates | Purification routing, charity payable, suspense clearing, reserve appropriation |
| Validators | Asset-assigned-at-value-date check; cross-pool transfer authorisation check; allocation-run-signed-before-fee check |
| Events | `allocation.anomaly.suspected` → Mizan agent |

### 30.2 SHA break codes (pack mein define honge)

| Code | Break |
| --- | --- |
| SHA-01 | Interest ya markup credit placement/nostro account par |
| SHA-02 | Late-payment charge collect hua, charity payable mein route nahi hua |
| SHA-03 | Non-permissible income distributable profit base mein shamil |
| SHA-04 | Purification payable settle hua bina disbursement evidence |
| SHA-05 | Do pools ke darmiyan cash movement bina approved transfer instruction |
| SHA-06 | Us asset se income jo value date par pool mein assigned nahi tha |
| SHA-07 | Mudarib/Wakalah fee allocation run sign hone se pehle settle |
| SHA-08 | Qard circle payout mein time-based uplift |

### 30.3 Mizan handoff contract

Recon break aksar allocation anomaly ki alamat hoti hai. Do agents ko ek doosre se takrana nahi chahiye.

```
Reconciliation Agent  ──(event)──►  Mizan Allocation Agent
  break: SHA-05, SHA-06, CLS-05, CLS-06
  payload: { break_id, pool_id, period, amount, evidence_refs }

Mizan Agent  ──(event)──►  Reconciliation Agent
  allocation anomaly detected → create linked break for cash-side verification
```

Rule: **ek case ka ek owner.** Jo agent pehle detect kare wo owner banta hai; doosra linked case banata hai, duplicate nahi. UI dono ko ek hi case thread mein dikhati hai.

### 30.4 Pack install ke waqt kya verify hoga

- `engine_compat` core version se match kare.
- Sab dimensions registry mein register hon aur koi collision na ho.
- SHA codes core codes se namespace clash na karen.
- Dry-run 3 mahine ke pool data par chale; diff report Shariah Secretariat + Finance dono sign karein.
- Cross-pool isolation constraint DB level par verify ho.

---

## 31. Decisions required

Coding se pehle ye finalize karna hai:

**Product**
1. Pehla target segment: banks, corporates, ya PSPs? (format library aur universe defaults isi se aayenge)
2. Pricing model: per-transaction, per-account, ya seat-based? (metering design isi se)
3. Deployment: SaaS-only, ya on-prem option din 1 se?

**Technical**
4. Base currency handling: single base per tenant ya multi-base?
5. FX revaluation break type v1 mein ya v2 mein?
6. Internal subledger v1 mein ya sirf external action reference?
7. LLM hosting: cloud API, private endpoint, ya both offered?
8. Vector store: pgvector (recommended) ya dedicated?

**Operational**
9. UAT ground-truth dataset kahan se aayega? (back-test ke baghair auto-match ship nahi ho sakta)
10. Pilot customer kaun hai aur kaun sa account?
11. Data retention aur residency requirements?
12. Kaun business owner tolerance profiles approve karega?

Bina 9 aur 10 ke demo to ban jayega, lekin auto-match production mein nahi ja sakta — kyunki false-match budget measure hi nahi hoga.

---

## 32. Configuration — kuch bhi hardcode nahi

Ye sab config se aayein, code se nahi: allowed source types aur schemas; currency aur timezone rules; tolerance profiles; matching layer priorities; confidence band thresholds; false-match budget; queue priority weights (w1–w5); agent budgets (cases, tools, tokens, cost, wall clock); autonomy level per universe; approval limits aur routing; ageing aur escalation windows; suppress-rule max expiry; chunking aur retrieval parameters; model aur prompt versions; masking aur retention settings; close calendar aur certification thresholds.

Har configuration change audit hoti hai: actor, reason, previous value, new value, effective time. Tolerance aur band changes ko maker-checker chahiye — ye financial parameters hain.

---

## 33. Final control principle

> **Reconciliation Agent investigator hai, executor nahi. Wo records milata hai, evidence jama karta hai, differences explain karta hai, aur resolution propose karta hai — chahe khud se, schedule par, bina poochhe. Lekin koi bhi financial entry, write-off, ya certification hamesha authorized human ke haath mein rehti hai, aur agent ke paas wo karne ka tool hi maujood nahi hai.**

Agent hone ka matlab zyada autonomy hai — zyada authority nahi. Ye farq poore system ka bunyadi asool hai:

- Agent **kab** kaam kare — ye configuration hai.
- Agent **kitna** kaam kare — ye budget hai.
- Agent **kya** kaam kare — ye architecture hai, aur wo badalti nahi.

---

*Document ends.*
