"""LAYER: PLANNER. Declares the canonical tool chain for each intent (fixed, not LLM-generated).
Used for the fail-fast permission check before any tool runs."""
from dataclasses import dataclass
from typing import Optional

CHAINS = {
    "SALES_RECO":        ["hot_picks", "compliance_filter"],                    # Chain A
    "COMPLIANCE_CHECK":  ["compliance_filter", "hot_picks"],                    # Chain B (+ alternatives)
    "VENDOR_ONBOARDING": ["vendor_validate"],                                   # Chain C
    "OPS_STOCK":         ["stock_by_warehouse"],
    "GENERAL_KB":        ["kb_search"],
}
ACTION_CHAINS = {"ADD_TO_BASKET": ["compliance_filter", "add_to_basket_stub"]}


@dataclass
class Plan:
    intent: str
    action: Optional[str]
    lane: str
    tools: list


def make_plan(route) -> Plan:
    tools = ACTION_CHAINS.get(route.action) or CHAINS[route.intent]
    return Plan(route.intent, route.action, route.lane, list(tools))
