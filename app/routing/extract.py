"""Entity extraction with regex. Cheap, deterministic, no LLM."""
import re
from ..execution import tools as T

STATE_NAMES = {"alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT",
    "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC"}
_NAMES = sorted(STATE_NAMES, key=len, reverse=True)           # "west virginia" before "virginia"
CODES = set(STATE_NAMES.values())
AMBIGUOUS = {"IN", "OR", "OK", "ME", "HI", "OH", "LA", "DE"}   # also common English words
ORDINALS = {"first": 0, "1st": 0, "top": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "last": -1}


def extract_state(q):
    m = re.search(r"\b(?i:in|for|to|from)\s+([A-Z]{2})\b", q)
    if m and m.group(1) in CODES:
        return m.group(1)
    ql = q.lower()
    for name in _NAMES:
        if re.search(rf"\b{name}\b", ql):
            return STATE_NAMES[name]
    return next((t for t in re.findall(r"\b[A-Z]{2}\b", q) if t in CODES and t not in AMBIGUOUS), None)


def extract_budget(q):
    m = (re.search(r"(?:under|below|less than|within|up to|max(?:imum)?|budget(?: of)?)\s*\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?\b", q, re.I)
         or re.search(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?\b", q, re.I))
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return v * 1000 if m.group(2) else v


def extract_limit(q):
    m = re.search(r"\btop\s+(\d+)\b", q, re.I) or re.search(r"\b(\d+)\s+(?:hot\s+)?(?:picks|products|items|recommendations)\b", q, re.I)
    return max(1, min(int(m.group(1)), 20)) if m else 5


def resolve_products(q):
    """-> (product_ids, unknown_skus). Matches SKU-123 first, then exact product names."""
    d, ids, unknown = T.data(), [], []
    for m in re.finditer(r"SKU[-\s]?(\d+)", q, re.I):
        p = d["by_sku"].get(f"SKU-{m.group(1)}")
        if p is None:
            unknown.append(f"SKU-{m.group(1)}")
        elif p["product_id"] not in ids:
            ids.append(p["product_id"])
    if not ids and not unknown:
        ql = q.lower()
        ids = [p["product_id"] for p in d["products"] if p["name"].lower() in ql]
    return ids, unknown


def pick_ordinal(q):
    return next((w for w in re.findall(r"[a-z0-9]+", q.lower()) if w in ORDINALS), None)


def extract_qty(q):
    m = re.search(r"\badd\s+(\d+)", q, re.I)
    return max(1, min(int(m.group(1)), 999)) if m else 1


def parse_vendor_text(q):
    """Free text -> attributes. Fields the user did not mention are ASSUMED present (and we say so)."""
    ql = q.lower()
    a = {"name": "(unspecified)", "category": "Unspecified", "net_wt_oz": 1, "net_vol_ml": 1, "nicotine_mg": 0,
         "images": True, "lab_report_attached": True}
    for cat, kw in [("THC Beverage", "thc"), ("CBD Gummies", "cbd"), ("Kratom", "kratom"), ("Mushroom", "mushroom"), ("Nicotine Vape", "nicotine")]:
        if kw in ql:
            a["category"] = cat
    if re.search(r"(missing|no|without)\s+net\s?(wt|weight)", ql):
        a["net_wt_oz"] = None
    if re.search(r"(missing|no|without)\s+net\s?vol", ql):
        a["net_vol_ml"] = None
    if "lab report" in ql or re.search(r"\bcoa\b", ql):
        a["lab_report_required"] = True
        a["lab_report_attached"] = not re.search(r"(missing|no|without|not)\s+(a\s+)?(lab report|coa)", ql)
    if re.search(r"(missing|no|without)\s+image", ql):
        a["images"] = False
    return a
