# Reelo AI — Tool-First AI Orchestration Layer over Odoo (PoC)

> **Assignment:** Odoo + AI/LLM Engineer Practical Test
> **Architecture:** Tool-First | Compliance-Driven | Deterministic | Lightweight
> **Dependencies:** None (Python 3.10+ standard library only)

---

## Problem Statement

Modern ERP systems like Odoo hold business-critical data — products, inventory, vendors, compliance policies. Traditional
LLM chat systems hallucinate business facts, send huge datasets to the model, produce inconsistent compliance decisions, and
have poor observability.

This PoC builds a lightweight orchestration layer where **tools decide facts, and the LLM (if added) only formats**. Every
business answer comes from a deterministic tool with a fixed contract. No LLM is called in this PoC; `formatter.llm_prompt()`
shows where one would slot in, with PII redaction and a 4000-char cap already in place.

---

## Quick Start

```bash
# Run the live demo (6 scenarios: sales, memory follow-up, compliance, stock, vendor, permission denial)
python main.py

# Interactive chat (optional user_type: internal_sales | portal_vendor | portal_customer)
python main.py chat internal_sales
```

No `pip install` needed — the project uses only the Python standard library.

Logs are written to `logs/traces.jsonl` (one line per request) and `logs/audit.jsonl` (one line per tool call).
To use your own data, replace `data/seed_data.json` or set `SEED_PATH=/path/to/your_data.json`.

---

## System Architecture

```
request -> ROUTE -> PLAN -> AUTHORIZE -> EXECUTE -> VALIDATE -> FORMAT -> PERSIST
           │         │          │           │          │          │          │
        regex     fixed     allowlist    chains    invariant   templates   session
        router    chains    per role    A/B/C     re-checks    + LLM hook  + trace
        0 tokens            + call     + stock                 redacted    + audit
                          time gate    + kb                   prompt cap
```

### Two Lanes

| Lane | Intent | Source of Truth |
|------|--------|-----------------|
| **TRUTH** | SALES_RECO, COMPLIANCE_CHECK, OPS_STOCK, VENDOR_ONBOARDING | Deterministic tools only — no LLM, no hallucination |
| **KNOWLEDGE** | GENERAL_KB | Keyword search over `kb_docs` (filtered by user visibility) |

### The 7-Stage Pipeline

1. **Route** — Regex picks exactly one of 5 intents and a lane. Zero LLM calls, zero tokens. First match wins.
2. **Plan** — A fixed table maps intent to a canonical tool chain (Chain A/B/C, stock, or kb). Not LLM-generated, so it's testable.
3. **Authorize** — Every tool in the plan must be in the caller's allowlist, else **DENIED before anything runs**. Checked again at call time.
4. **Execute** — The chain runs; every tool call goes through `ToolRunner` (allowlist enforcement, timing, trace, audit log).
5. **Validate** — An independent post-check: nothing is recommended or staged unless `compliance_filter` said ALLOWED in *this* request.
6. **Format** — Deterministic templates. An LLM, if added, would only rephrase the redacted, size-capped tool result.
7. **Persist** — Session memory updated only on success; one trace line per request, one audit line per tool call.

---

## Project Structure

```
reelo_ai_poc/
├── main.py                          entry point (demo / chat modes)
├── data/
│   └── seed_data.json               input data (products, inventory, customers, vendors, kb_docs)
├── docs/
│   ├── architecture.png
│   └── TECHNICAL_NOTE.md
├── logs/                             written at runtime
│   ├── traces.jsonl                  one JSON line per request
│   └── audit.jsonl                   one JSON line per tool call
└── app/
    ├── __init__.py
    ├── engine.py                     orchestrator pipeline (route -> authorize -> execute -> validate -> format -> persist)
    ├── routing/
    │   ├── __init__.py
    │   ├── router.py                  intent classification (regex, 5 intents, first match wins)
    │   ├── planner.py                 canonical chain selection per intent
    │   └── extract.py                 entity extraction (state, budget, SKU, ordinals, vendor text parsing)
    ├── execution/
    │   ├── __init__.py
    │   ├── chains.py                  canonical workflows: sales (A), compliance (B), vendor (C), stock, kb, basket
    │   ├── runner.py                  the single gate every tool call passes through (allowlist + timing + audit)
    │   └── tools.py                   5 deterministic business tools + basket stub
    ├── safety/
    │   ├── __init__.py
    │   ├── policy.py                  per-user_type tool allowlist + KB doc visibility
    │   ├── validator.py               independent post-execution invariant check
    │   └── pii.py                     PII redaction (email, phone) for logs and LLM prompts
    ├── state/
    │   ├── __init__.py
    │   └── state.py                   per-session memory (in-memory; Redis in production)
    ├── output/
    │   ├── __init__.py
    │   └── formatter.py               response templates + LLM prompt builder (redacted, size-capped)
    └── observability/
        ├── __init__.py
        └── observability.py           structured traces + audit logs (output hashing, PII redaction)
```

---

## File Responsibilities

| File | Responsibility |
|------|----------------|
| `main.py` | Entry point — runs demo or interactive chat |
| `app/routing/router.py` | Intent classification (regex, 5 intents, zero LLM) |
| `app/routing/planner.py` | Maps intent to canonical tool chain |
| `app/routing/extract.py` | Entity extraction (state, budget, SKU, ordinals, vendor text) |
| `app/execution/chains.py` | Canonical workflows (Chain A/B/C, stock, kb, basket) |
| `app/execution/runner.py` | Tool execution gate (allowlist + timing + trace + audit) |
| `app/execution/tools.py` | 5 deterministic business tools + basket stub |
| `app/engine.py` | 7-stage orchestration pipeline |
| `app/safety/policy.py` | Per-role tool allowlist + KB visibility |
| `app/safety/validator.py` | Post-execution invariant checks |
| `app/safety/pii.py` | PII redaction (email, phone) |
| `app/state/state.py` | Per-session memory (last_intent, last_state, last_budget, last_product_ids) |
| `app/output/formatter.py` | Response templates + LLM prompt builder (redacted, 4000-char cap) |
| `app/observability/observability.py` | Structured traces + audit logs with output hashing |

---

## Intent Router

| Intent | Lane | Trigger Keywords (regex, first match wins) |
|--------|------|---------------------------------------------|
| `SALES_RECO` (+ ADD_TO_BASKET) | TRUTH | `add ... basket/cart` |
| `VENDOR_ONBOARDING` | TRUTH | `uploading, onboard, lab report, net wt, vendor` |
| `OPS_STOCK` | TRUTH | `stock, inventory, warehouse, how many, how much ... have/left` |
| `COMPLIANCE_CHECK` | TRUTH | `blocked, legal, illegal, compliance, restricted, why is` |
| `SALES_RECO` | TRUTH | `hot picks, recommend, best sellers, under $, suggest` |
| `GENERAL_KB` (fallback) | KNOWLEDGE | anything that doesn't match above |

---

## Business Tools

All tools are deterministic pure functions with fixed contracts. In production, each becomes an Odoo RPC/REST call
without changing the orchestrator.

| Tool | Input | Output |
|------|-------|--------|
| `hot_picks(state, budget, limit)` | destination state, max price, result count | ranked products by popularity (slim view) |
| `compliance_filter(state, product_ids)` | destination state, product IDs | ALLOWED / BLOCKED / REVIEW + reason_code per product |
| `stock_by_warehouse(product_id)` | product ID | per-warehouse quantities + total |
| `vendor_validate(attributes_json)` | product attributes dict | PASS / FAIL / REVIEW + missing fields + required docs |
| `kb_search(query, top_k, visibilities)` | free text, result count, allowed visibilities | ranked KB doc snippets |
| `add_to_basket_stub(product_id, qty)` | product ID, quantity | staged basket item (stub — production: Odoo `sale.order.line`) |

### Compliance Model

`compliance_filter` is the **only** place compliance is decided:

| Status | Meaning | reason_code examples |
|--------|---------|---------------------|
| `ALLOWED` | No restriction found | `OK` |
| `BLOCKED` | State law prohibits sale | `STATE_BLOCKED_CA`, `STATE_BLOCKED_FL` |
| `REVIEW` | Needs manual verification | `LAB_REPORT_REQUIRED`, `UNKNOWN_PRODUCT`, `STATE_UNKNOWN` |

BLOCKED and REVIEW items are never recommended. The validator independently re-checks this after execution.

---

## Canonical Chains

**Chain A — Sales Recommendation:**
```
hot_picks (over-fetch 3x) -> compliance_filter -> keep only ALLOWED -> return top N
```

**Chain B — Compliance Check:**
```
resolve SKU -> compliance_filter -> if BLOCKED/REVIEW: hot_picks(same category) -> compliance_filter alternatives
```

**Chain C — Vendor Onboarding:**
```
vendor_validate -> checklist (missing fields + required documents + warnings)
```

**Memory Follow-Up (ADD_TO_BASKET):**
```
resolve ordinal from last_product_ids -> compliance_filter re-check -> add_to_basket_stub
```

---

## Session State

Stored per `session_id` (in-memory dict, 30-min TTL):

| Field | Purpose |
|-------|---------|
| `last_intent` | Previous intent for follow-up context |
| `last_state` | Destination state (so "add 2 of the first one" knows where to check compliance) |
| `last_budget` | Previous budget filter |
| `last_product_ids` | Ordered list from last recommendation (resolves "first", "second", "last") |

Memory is written **only after the validator passes** — a bad result never poisons follow-ups.

---

## Security

| Mechanism | Where | What it does |
|-----------|-------|-------------|
| Tool allowlist | `policy.py` + `engine.py` (plan time) + `runner.py` (call time) | Each user_type has a set of allowed tools; missing user_type defaults to least privilege (`portal_customer`) |
| KB visibility | `policy.py` | Filters KB docs by visibility: `internal_sales` sees all, `portal_vendor` sees `public` + `vendor`, `portal_customer` sees `public` only |
| PII redaction | `pii.py` | Email and phone redacted from logs and any LLM prompt |
| Audit logging | `observability.py` | Every tool call logged with args hash + output hash (no raw payload) |
| Validator | `validator.py` | Independent re-check: nothing recommended without ALLOWED verdict |

### Role Permissions

| Tool | internal_sales | portal_vendor | portal_customer |
|------|:-:|:-:|:-:|
| hot_picks | ✅ | ❌ | ✅ |
| compliance_filter | ✅ | ❌ | ✅ |
| stock_by_warehouse | ✅ | ❌ | ❌ |
| vendor_validate | ✅ | ✅ | ❌ |
| kb_search | ✅ | ✅ | ✅ |
| add_to_basket_stub | ✅ | ❌ | ✅ |

---

## Observability

Every request writes two log files:

**`logs/traces.jsonl`** — one line per request:
```json
{"ts": "...", "request_id": "d17ee91c622d", "session_id": "s1", "user_type": "internal_sales",
 "intent": "SALES_RECO", "lane": "TRUTH", "status": "OK", "query": "Give me hot picks for CA under $5000",
 "tools_called": [{"tool": "hot_picks", "args": {...}, "latency_ms": 0.198, "output_hash": "6349441082a0ad38"}],
 "denied_tools": [], "validation_failures": [], "latency_ms_total": 12.16, "prompt_tokens_est": 258}
```

**`logs/audit.jsonl`** — one line per tool call:
```json
{"ts": "...", "request_id": "d17ee91c622d", "user_type": "internal_sales", "tool": "hot_picks",
 "allowed": true, "args_hash": "...", "output_hash": "..."}
```

Tool outputs are stored as **hashes only** (tamper-evident audit without storing payloads). Args are PII-redacted.
`prompt_tokens_est` = approximate token count an LLM call would cost (prompt length / 4).

---

## Demo Output

Running `python main.py` executes 6 scenarios:

```
[internal_sales] Give me hot picks for CA under $5000
 -> intent=SALES_RECO status=OK tools=['hot_picks', 'compliance_filter']
Top picks for CA under $5,000.00:
1. SKU-1013 - Accessories - Ember 86 - $256.69 (popularity 0.955)
2. SKU-1002 - Nicotine Vape - Cloud 433 - $229.66 (popularity 0.947)
3. SKU-1053 - Accessories - Ember 291 - $94.25 (popularity 0.906)
...
Excluded by compliance: 4 blocked, 2 need review.

[internal_sales] Ok add 2 of the first one to the basket
 -> intent=SALES_RECO status=OK tools=['compliance_filter', 'add_to_basket_stub']
Staged 2 x SKU-1013 (Accessories - Ember 86). Compliance re-checked for CA: ALLOWED.
Basket write is a stub (executed=False).

[internal_sales] Why is SKU-1012 not available in CA? Suggest alternatives.
 -> intent=COMPLIANCE_CHECK status=OK tools=['compliance_filter', 'hot_picks', 'compliance_filter']
SKU-1012 (Mushroom Chocolate - Ember 93) in CA: BLOCKED - Blocked in CA [STATE_BLOCKED_CA]
  Allowed alternatives: SKU-1027 (Mushroom Chocolate - Ember 122, $44.90); ...

[internal_sales] How much stock does SKU-1001 have and where?
 -> intent=OPS_STOCK status=OK tools=['stock_by_warehouse']
SKU-1001 (THC Beverage - Cloud 430): total 471 -> NY: 222, LA: 214, TX: 35

[portal_vendor] I'm uploading a product missing Net Wt and no lab report - what do I fix?
 -> intent=VENDOR_ONBOARDING status=OK tools=['vendor_validate']
Validation status: FAIL
  [x] name  [x] category  [ ] net_wt_oz  [x] net_vol_ml  [ ] Lab Report
Fix these fields: net_wt_oz
Upload these documents: Lab Report

[portal_customer] How much stock does SKU-1001 have?
 -> intent=OPS_STOCK status=DENIED tools=[]
Permission denied: 'portal_customer' cannot use stock_by_warehouse.
```

---

## Sample Queries

| Intent | Example Query |
|--------|---------------|
| Sales | `Give me hot picks for CA under $5000` |
| Memory follow-up | `Ok add 2 of the first one to the basket` |
| Compliance | `Why is SKU-1012 not available in CA? Suggest alternatives.` |
| Stock | `How much stock does SKU-1001 have and where?` |
| Vendor | `I'm uploading a product missing Net Wt and no lab report - what do I fix?` |
| Knowledge | `What is the return policy?` (falls through to GENERAL_KB) |

### Programmatic API (vendor validation with structured input)

```python
from app.engine import Orchestrator
o = Orchestrator()
r = o.handle({
    "user_type": "portal_vendor",
    "session_id": "s1",
    "query": "validate my product",
    "attributes": {"name": "Cloud Vape", "category": "Nicotine Vape",
                   "net_wt_oz": 2.5, "net_vol_ml": 30, "nicotine_mg": 20,
                   "lab_report_attached": False, "lab_report_required": True,
                   "images": True}
})
print(r["answer"])
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SEED_PATH` | `data/seed_data.json` | Path to the seed data file |
| `LOG_DIR` | `logs/` | Directory for trace and audit logs |
| `LOG_STDERR` | `1` | Set to `0` to suppress TRACE lines on stderr |

---

## Design Decisions

| Decision | Why | Trade-off |
|----------|-----|-----------|
| Regex router, no LLM | Cheap, deterministic, testable | Weaker on unusual phrasing; add a small classifier as fallback later |
| Templates for answers | No hallucination, zero tokens | Less conversational; LLM rephrase can be added behind the validator |
| Over-fetch 3x then filter | Enough ALLOWED items remain after blocked ones are removed | Slightly more reads |
| REVIEW is not recommended | Safer: an unverified lab report cannot be sold | May hide items ops could clear manually |
| Memory written after validation | A bad result never poisons follow-ups | One extra step |
| Compliance decided in one place | Single source of truth, auditable | Must route all product questions through `compliance_filter` |
| Output hashing in logs | Tamper-evident audit without storing payloads | Can't inspect raw output from logs (by design) |

---

## Data Source

The system reads from `data/seed_data.json` which contains:
- **products** — id, sku, name, category, flags, blocked_states, lab_report_required, price, popularity_score
- **inventory** — product_id, warehouse, qty
- **customers** — user profiles
- **vendors** — vendor profiles
- **kb_docs** — doc_id, title, text, visibility (public / vendor / internal)

---

## Known Limits

- The basket is a stub (the assignment defines no basket tool).
- Free-text vendor checks assume unmentioned fields are present (and say so).
- No LLM is called in this PoC — `formatter.llm_prompt()` shows where one would slot in.
- Observability is structured logs (Langfuse not used).
- Session state is in-memory (Redis in production).

---

## Technologies Used

**Language:** Python 3.10+
**Standard Libraries:** `json`, `pathlib`, `hashlib`, `re`, `typing`, `dataclasses`, `collections`, `uuid`, `time`, `os`, `sys`, `contextlib`

---

## Future Improvements

- FastAPI REST wrapper with OpenAPI docs
- PostgreSQL for persistent data; Redis for session state and read cache
- Docker + Kubernetes deployment (stateless orchestrator pods)
- Async tool execution with per-tool timeouts and circuit breakers
- Distributed tracing (Langfuse / OpenTelemetry) + metrics dashboard
- LLM formatting layer behind the validator (redacted, size-capped prompt only)
- Golden test suite in CI (intent accuracy + tool-chain match rate)
- Authentication and authorization (JWT / OAuth)
- CI/CD pipeline with automated compliance rule versioning

---

## Author

**Apeksha Chandak** — AI Automation Engineer | Python Full Stack Developer
