"""LAYER: VALIDATOR. Independent post-check on what we are about to return.
Business invariant: nothing recommended / staged / offered as an alternative unless the
compliance_filter output in this request says ALLOWED."""


def _allowed_ids(trace, state):
    ok = set()
    for name, _args, out in trace.outputs:
        if name == "compliance_filter":
            ok |= {v["product_id"] for v in out if v["status"] == "ALLOWED" and v["state"] == state}
    return ok


def validate_invariants(ctx) -> list:
    p, problems = ctx.payload, []
    if ctx.status != "OK":
        return problems
    if ctx.route.action == "ADD_TO_BASKET":
        if p["basket"]["product_id"] not in _allowed_ids(ctx.trace, p["state"]):
            problems.append("basket item not verified ALLOWED")
    elif ctx.route.intent == "SALES_RECO":
        ok = _allowed_ids(ctx.trace, p["state"])
        problems += [f"recommended {r['sku']} without ALLOWED verdict" for r in p["recommendations"] if r["product_id"] not in ok]
    elif ctx.route.intent == "COMPLIANCE_CHECK":
        ok = _allowed_ids(ctx.trace, p["state"])
        problems += [f"alternative {a['sku']} without ALLOWED verdict" for alts in p["alternatives"].values()
                     for a in alts if a["product_id"] not in ok]
    return problems
