"""LAYER: ROUTER. Cheap intent classification: regex only, ZERO LLM calls. First match wins => exactly one intent."""
import re
from dataclasses import dataclass
from typing import Optional

RULES = [
    ("SALES_RECO", "ADD_TO_BASKET", r"\badd\b.*\b(basket|cart)\b"),
    ("VENDOR_ONBOARDING", None, r"\b(uploading|upload|onboard\w*|lab report|net\s?(wt|weight|vol\w*)|my product|vendor)\b"),
    ("OPS_STOCK", None, r"\b(stock|inventory|warehouse|in hand|on hand|how many)\b|how much .* (have|left)"),
    ("COMPLIANCE_CHECK", None, r"\b(blocked|legal|illegal|compliance|compliant|allowed|not available|restricted|why is)\b"),
    ("SALES_RECO", None, r"\b(hot picks?|recommend\w*|best sellers?|top \d+|popular|under \$?\d|budget|suggest)\b"),
]


@dataclass
class Route:
    intent: str
    action: Optional[str]
    lane: str            # TRUTH = facts must come from tools | KNOWLEDGE = document lookup


def classify(q: str) -> Route:
    ql = q.lower()
    for intent, action, pat in RULES:
        if re.search(pat, ql):
            return Route(intent, action, "TRUTH")
    return Route("GENERAL_KB", None, "KNOWLEDGE")
