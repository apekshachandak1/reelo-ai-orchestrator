"""LAYER: TOOLS. Deterministic business logic over seed_data.json. No LLM in this file, ever.
Each tool has ONE responsibility. In production each becomes an Odoo/REST call with the same contract."""
import json, os, re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SEED_PATH = Path(os.getenv("SEED_PATH", ROOT / "data" / "seed_data.json"))
LAB_REPORT_CATEGORIES = ("thc", "cbd", "kratom", "mushroom")
VENDOR_KNOWN = {"name", "category", "net_wt_oz", "net_vol_ml", "nicotine_mg", "lab_report_attached",
                "lab_report_required", "images", "state_restrictions"}
_DATA = None


def _load_json(path):
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:                       # tolerate trailing commas in hand-edited seed files
        return json.loads(re.sub(r",(\s*[\]}])", r"\1", text))


def data():
    global _DATA
    if _DATA is None:
        raw = _load_json(SEED_PATH)
        inv = defaultdict(list)
        for r in raw.get("inventory", []):
            inv[r["product_id"]].append({"warehouse": r["warehouse"], "qty": r["qty"]})
        _DATA = {"products": raw["products"], "kb_docs": raw.get("kb_docs", []), "inv": inv,
                 "by_id": {p["product_id"]: p for p in raw["products"]},
                 "by_sku": {p["sku"].upper(): p for p in raw["products"]}}
    return _DATA


def _slim(p):
    return {"product_id": p["product_id"], "sku": p["sku"], "name": p["name"], "category": p["category"],
            "price": p["price"], "popularity_score": p["popularity_score"]}


# 1 ---------------------------------------------------------------- hot_picks
def hot_picks(state, budget, limit):
    """Rank by popularity_score among products priced <= budget. Does NOT check legality (by design)."""
    c = [p for p in data()["products"] if budget is None or p["price"] <= budget]
    c.sort(key=lambda p: (-p["popularity_score"], p["product_id"]))      # deterministic tie-break
    return [_slim(p) for p in c[:limit]]


# 2 --------------------------------------------------------- compliance_filter
def compliance_filter(state, product_ids):
    """ALLOWED / BLOCKED / REVIEW + reason_code. The ONLY place compliance is decided."""
    out = []
    for pid in product_ids:
        p = data()["by_id"].get(pid)
        if p is None:
            v = ("REVIEW", "UNKNOWN_PRODUCT", f"Product {pid} not found")
        elif not state:
            v = ("REVIEW", "STATE_UNKNOWN", "No destination state given")
        elif state in p["blocked_states"]:
            v = ("BLOCKED", f"STATE_BLOCKED_{state}", f"Blocked in {state}")
        elif p["lab_report_required"]:
            v = ("REVIEW", "LAB_REPORT_REQUIRED", "Lab report must be verified before sale")
        else:
            v = ("ALLOWED", "OK", "No restriction found")
        out.append({"product_id": pid, "sku": p["sku"] if p else None, "name": p["name"] if p else None,
                    "category": p["category"] if p else None, "state": state, "status": v[0],
                    "reason_code": v[1], "reason": v[2]})
    return out


# 3 -------------------------------------------------------- stock_by_warehouse
def stock_by_warehouse(product_id):
    p = data()["by_id"].get(product_id)
    if p is None:
        return {"product_id": product_id, "found": False, "warehouses": [], "total_qty": 0}
    wh = data()["inv"].get(product_id, [])
    return {"product_id": product_id, "sku": p["sku"], "name": p["name"], "found": True,
            "warehouses": wh, "total_qty": sum(w["qty"] for w in wh)}


# 4 ------------------------------------------------------------ vendor_validate
def vendor_validate(attributes_json):
    a = attributes_json or {}
    cat = (a.get("category") or "").lower()
    required = ["name", "category", "net_wt_oz", "net_vol_ml"]
    if "nicotine" in cat:
        required.append("nicotine_mg")
    missing = [f for f in required if a.get(f) in (None, "")]
    needs_lab = bool(a.get("lab_report_required")) or any(k in cat for k in LAB_REPORT_CATEGORIES)
    docs = ["Lab Report"] if needs_lab and not a.get("lab_report_attached") else []
    warnings = [w for w in ("images", "state_restrictions") if a.get(w) is False]
    status = "FAIL" if (missing or docs) else ("REVIEW" if warnings else "PASS")
    checklist = [{"item": f, "ok": f not in missing} for f in required]
    if needs_lab:
        checklist.append({"item": "Lab Report", "ok": not docs})
    return {"status": status, "missing_fields": missing, "required_documents": docs, "warnings": warnings,
            "checklist": checklist, "ignored_fields": sorted(k for k in a if k not in VENDOR_KNOWN)}


# 5 ------------------------------------------------------------------ kb_search
_STOP = {"the", "a", "is", "what", "how", "do", "i", "to", "of", "for", "and", "our", "your", "me", "we",
         "about", "policy", "sop", "guide"}


def kb_search(query, top_k=3, visibilities=None):
    toks = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if t not in _STOP and len(t) > 2}
    hits = []
    for d in data()["kb_docs"]:
        if visibilities is not None and d["visibility"] not in visibilities:
            continue
        title = set(re.findall(r"[a-z0-9]+", d["title"].lower()))
        text = set(re.findall(r"[a-z0-9]+", d["text"].lower()))
        score = 2 * len(toks & title) + len(toks & text)
        if score:
            hits.append({"doc_id": d["doc_id"], "title": d["title"], "snippet": d["text"][:240], "score": score})
    return sorted(hits, key=lambda h: -h["score"])[:top_k]


# basket: STUB (the assignment defines no basket tool) -------------------------
def add_to_basket_stub(product_id, qty):
    p = data()["by_id"][product_id]
    return {"action": "ADD_TO_BASKET", "product_id": product_id, "sku": p["sku"], "name": p["name"],
            "qty": qty, "executed": False, "note": "Stub. Production: create Odoo sale.order.line."}


TOOLS = {"hot_picks": hot_picks, "compliance_filter": compliance_filter, "stock_by_warehouse": stock_by_warehouse,
         "vendor_validate": vendor_validate, "kb_search": kb_search, "add_to_basket_stub": add_to_basket_stub}
