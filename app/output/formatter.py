"""LAYER: FORMATTER. Turns the tool payload into the final answer with deterministic templates.
The LLM would sit HERE in production and may only rephrase the (redacted, size-capped) tool result.
`llm_prompt()` shows where PII is redacted and how the prompt size is bounded and estimated."""
import json
from ..safety.pii import redact, redact_obj

MAX_PROMPT_CHARS = 4000
MESSAGE_STATUSES = ("NEEDS_INFO", "DENIED", "BLOCKED_ACTION", "ERROR")


def _money(x):
    return f"${x:,.2f}"


def llm_prompt(query, payload) -> str:
    """Redact PII + cap size. Only the small tool result is ever sent, never the dataset."""
    return f"Question: {redact(query)}\nTool result JSON: {json.dumps(redact_obj(payload), default=str)[:MAX_PROMPT_CHARS]}"


def render(intent, status, p, action=None) -> str:
    if status in MESSAGE_STATUSES:
        return p["message"]
    if action == "ADD_TO_BASKET":
        b = p["basket"]
        return (f"Staged {b['qty']} x {b['sku']} ({b['name']}). Compliance re-checked for {p['state']}: ALLOWED. "
                f"Basket write is a stub (executed={b['executed']}).")
    if intent == "SALES_RECO":
        if not p["recommendations"]:
            return f"No compliant products found for {p['state']}."
        lines = [f"Top picks for {p['state']}" + (f" under {_money(p['budget'])}" if p["budget"] else "") + ":"]
        lines += [f"{i}. {r['sku']} - {r['name']} - {_money(r['price'])} (popularity {r['popularity_score']})"
                  for i, r in enumerate(p["recommendations"], 1)]
        ex = p["excluded"]
        lines.append(f"Excluded by compliance: {ex['blocked']} blocked, {ex['review']} need review.")
        return "\n".join(lines)
    if intent == "COMPLIANCE_CHECK":
        lines = []
        for v in p["verdicts"]:
            lines.append(f"{v['sku']} ({v['name']}) in {v['state']}: {v['status']} - {v['reason']} [{v['reason_code']}]")
            if v["status"] != "ALLOWED":
                alts = p["alternatives"].get(str(v["product_id"]), [])
                lines.append("  Allowed alternatives: " + ("; ".join(f"{a['sku']} ({a['name']}, {_money(a['price'])})" for a in alts) or "none found"))
        return "\n".join(lines)
    if intent == "OPS_STOCK":
        lines = []
        for s in p["stock"]:
            if not s["found"]:
                lines.append(f"Product {s['product_id']} not found.")
            else:
                wh = ", ".join(f"{w['warehouse']}: {w['qty']}" for w in s["warehouses"]) or "no inventory records"
                lines.append(f"{s['sku']} ({s['name']}): total {s['total_qty']} -> {wh}")
        return "\n".join(lines)
    if intent == "VENDOR_ONBOARDING":
        r = p["result"]
        lines = [f"Validation status: {r['status']}"] + [f"  [{'x' if c['ok'] else ' '}] {c['item']}" for c in r["checklist"]]
        if r["missing_fields"]:
            lines.append("Fix these fields: " + ", ".join(r["missing_fields"]))
        if r["required_documents"]:
            lines.append("Upload these documents: " + ", ".join(r["required_documents"]))
        if r["warnings"]:
            lines.append("Recommended: " + ", ".join(r["warnings"]))
        if p["assumptions"]:
            lines.append("Note: " + p["assumptions"])
        return "\n".join(lines)
    if intent == "GENERAL_KB":
        return "\n".join(f"- {r['title']}: {r['snippet']}" for r in p["results"]) or "No matching document found."
    return json.dumps(p, default=str)


def format_answer(intent, status, payload, query, trace, action=None):
    if status == "OK":
        trace.prompt_tokens_est = len(llm_prompt(query, payload)) // 4   # tokens an LLM call WOULD cost (approx)
    return render(intent, status, payload, action)
