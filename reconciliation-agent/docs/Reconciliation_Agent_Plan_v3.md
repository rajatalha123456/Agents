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
| Auto-match | "Exact rule pass = Matched" | **Confidence bands + false-match budget + circuit breaker** | Financial recon mein false match sabse mehnga error hai |
| Close cycle | Nahi tha | **Period close, certification, roll-forward** | Standalone recon product isi par bikta hai |
| Bank formats | CSV/Excel | + **MT940, CAMT.053, BAI2, ISO 20022** | Banking ki default zubaan |
| Multi-tenancy | Zikr tha, faisla nahi | **Shared schema + RLS** (decision recorded) | Baad mein migrate karna mehnga hai |
| Guardrail | FR-021 requirement | FR-021 + **CI architecture test** jo build fail karta hai | Requirement jo test nahi hoti wo requirement nahi hoti |

v2 ki jo cheezein waise ki waise carry ho rahi hain: rule-first architecture, do data paths (SQL = facts, RAG = knowledge), structured JSON output with backend ID validation, decimal money, raw+normalized dual storage, idempotent imports, immutable audit.

---

## 1. Product decision: Agent, Copilot nahi

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

| Level | Naam | Agent kya karta hai | Default |
| --- | --- | --- | --- |
| A0 | Observe | Sirf run karta hai, matching karta hai, kuch propose nahi karta | Onboarding ke pehle 2 hafte |
| A1 | Propose on demand | Human ke kehne par ek case analyze karta hai (v2 wala behaviour) | Fallback jab schedule off ho |
| A2 | Propose on schedule | Har run ke baad poori queue triage karta hai, ranked proposals tayyar karta hai | Production default |
| A3 | Auto-match | A2 + whitelisted universes mein high-confidence deterministic matches khud confirm karta hai | Opt-in, per universe, after back-test |

**A4 (auto-post) ka wajood hi nahi hai.**

### 1.3 Agent run loop

```
SENSE -> PLAN -> ACT -> PROPOSE -> PARK
```

Har phase par budget lagta hai (§11.4). Budget khatam hone par agent rukta hai aur jo bacha hai use `NOT_ANALYSED` mark karta hai.

### 1.4 Queue prioritisation formula

```
priority = w1*log10(1 + |amount|)
         + w2*break_type.risk_weight
         + w3*age_days
         + w4*close_deadline_pressure
         + w5*(1 if repeat_counterparty_break else 0)
```

Weights configuration se aate hain (§32).

---

## 2. Architecture principle: Core + Rule Packs

### 2.2 Non-negotiable rule

Core mein kisi domain ka naam nahi aayega (na `pool`, na `mudarabah`, na `policy_premium`, na `claim`). CI mein banned-vocabulary lint enforce hota hai.

### 2.4 Extension points (day 1)

| # | Extension point |
| --- | --- |
| EP-01 | `dimensions` JSONB canonical record par + indexable dimension registry |
| EP-02 | Break type registry as data (table, not enum) |
| EP-03 | `is_sensitive` flag har break type par |
| EP-04 | Routing rules table: (break_family, amount_band, dimension_filter) -> role |
| EP-05 | Validator/enricher plugin hook, normalization ke baad |
| EP-06 | Knowledge corpus namespacing per pack |
| EP-07 | Journal draft template registry |
| EP-08 | Universe definitions as data |
| EP-09 | Outbound event bus |
| EP-10 | Evidence type registry |

---

## 3. Scope

Full in-scope / permanently-out-of-scope / v1-deferred lists — see §3.1–3.3 of the source document. Key permanent exclusions: agent never posts financial entries, never executes write-offs, never edits/deletes source transactions, never releases payment, never bypasses human approval, never changes its own autonomy or budget, never accesses source-system credentials.

---

## 4–33

The remaining sections (domain model, pack contract, ingestion formats, normalization, matching engine, confidence bands, break taxonomy of 48 codes, agent runtime, tool registry, guardrails, resolution paths, period close, roll-forward, onboarding, human workflow, RAG, multi-tenancy, dashboard, API surface, audit, metrics, LLM economics, security/NFR, tech stack, delivery roadmap, test plan, Mizan pack, open decisions, configuration, and the final control principle) are implemented incrementally against this repository. Section numbers are referenced directly in code comments, docstrings, and test names throughout `backend/` so the spec and the implementation stay traceable to each other.

Keep the full original text (as supplied to the coding agent) next to this file or in your team wiki as the canonical reference — this in-repo copy's purpose is traceability of section numbers, not being the sole copy.
