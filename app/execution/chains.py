"""LAYER: CHAINS. The canonical tool chains. Each handler returns (status, payload) and may set ctx.updates
(session memory writes are applied ONLY after the validator passes). All tool calls go through ToolRunner."""
from ..routing import extract as X
from ..safety.policy import KB_VISIBILITY


class Chains:
    def __init__(self, runner):
        self.r = runner

    def _call(self, ctx, name, **kw):
        return self.r.call(ctx.trace, ctx.user_type, name, **kw)

    def _allowed_subset(self, ctx, state, cands):
        """compliance_filter a candidate list -> (allowed candidates, verdict map)."""
        if not cands:
            return [], {}
        v = {x["product_id"]: x for x in self._call(ctx, "compliance_filter", state=state, product_ids=[c["product_id"] for c in cands])}
        return [c for c in cands if v[c["product_id"]]["status"] == "ALLOWED"], v

    # ---- Chain A: hot_picks -> compliance_filter -> response
    def sales(self, ctx):
        s, q = ctx.sess, ctx.query
        state, budget, limit = X.extract_state(q) or s.last_state, X.extract_budget(q) or s.last_budget, X.extract_limit(q)
        if not state:
            return "NEEDS_INFO", {"message": "Which state are you selling to? (e.g. CA)"}
        cands = self._call(ctx, "hot_picks", state=state, budget=budget, limit=limit * 3)      # over-fetch: some get filtered out
        allowed, verdicts = self._allowed_subset(ctx, state, cands)
        recs = [dict(c, compliance="ALLOWED") for c in allowed[:limit]]
        ctx.updates = {"last_state": state, "last_budget": budget, "last_product_ids": [r["product_id"] for r in recs]}
        return "OK", {"state": state, "budget": budget, "recommendations": recs,
                      "excluded": {"blocked": sum(v["status"] == "BLOCKED" for v in verdicts.values()),
                                   "review": sum(v["status"] == "REVIEW" for v in verdicts.values())}}

    # ---- Chain B: find product -> compliance_filter -> reasons + ALLOWED alternatives
    def compliance(self, ctx):
        s, q = ctx.sess, ctx.query
        ids, unknown = X.resolve_products(q)
        if unknown and not ids:
            return "NEEDS_INFO", {"message": f"I couldn't find {', '.join(unknown)} in the catalog."}
        ids = ids or s.last_product_ids[:1]
        state = X.extract_state(q) or s.last_state
        if not ids or not state:
            return "NEEDS_INFO", {"message": "Please give me a SKU and a state, e.g. 'Why is SKU-1002 blocked in CA?'"}
        verdicts = self._call(ctx, "compliance_filter", state=state, product_ids=ids)
        alts, per_cat = {}, {}
        for v in verdicts:
            if v["status"] == "ALLOWED":
                continue
            cat = v["category"]
            if cat not in per_cat:
                pool = [c for c in self._call(ctx, "hot_picks", state=state, budget=None, limit=60) if c["product_id"] not in ids]
                same = [c for c in pool if c["category"] == cat]
                for cands in (same, pool):                         # same category first, then anything
                    per_cat[cat] = self._allowed_subset(ctx, state, cands)[0][:3]
                    if per_cat[cat]:
                        break
            alts[str(v["product_id"])] = per_cat[cat]
        ctx.updates = {"last_state": state, "last_product_ids": ids}
        return "OK", {"state": state, "verdicts": verdicts, "alternatives": alts}

    # ---- single tool: stock
    def stock(self, ctx):
        ids, unknown = X.resolve_products(ctx.query)
        if unknown and not ids:
            return "NEEDS_INFO", {"message": f"I couldn't find {', '.join(unknown)} in the catalog."}
        ids = ids or ctx.sess.last_product_ids[:1]
        if not ids:
            return "NEEDS_INFO", {"message": "Which SKU? e.g. 'How much stock does SKU-1001 have?'"}
        stock = [self._call(ctx, "stock_by_warehouse", product_id=i) for i in ids]
        ctx.updates = {"last_product_ids": ids}
        return "OK", {"stock": stock}

    # ---- Chain C: vendor_validate -> checklist
    def vendor(self, ctx):
        attrs = ctx.req.get("attributes")
        assumptions = "" if attrs else ("Fields you didn't mention were assumed present. "
                                         "Send the full attributes JSON for a complete check.")
        result = self._call(ctx, "vendor_validate", attributes_json=attrs or X.parse_vendor_text(ctx.query))
        return "OK", {"result": result, "assumptions": assumptions}

    # ---- knowledge lane
    def kb(self, ctx):
        res = self._call(ctx, "kb_search", query=ctx.query, top_k=3, visibilities=KB_VISIBILITY[ctx.user_type])
        return "OK", {"results": res}

    # ---- memory follow-up: "Ok add 2 of the first one to the basket"
    def basket(self, ctx):
        s, q = ctx.sess, ctx.query
        ids = s.last_product_ids
        if not ids:
            return "NEEDS_INFO", {"message": "I don't have a previous list yet. Ask for hot picks first."}
        word = X.pick_ordinal(q)
        if word is None and len(ids) > 1:
            return "NEEDS_INFO", {"message": "Which one? Say 'first', 'second', or give a SKU."}
        idx = X.ORDINALS[word] if word else 0
        if not -len(ids) <= idx < len(ids):
            return "NEEDS_INFO", {"message": f"I only have {len(ids)} item(s) from the last list."}
        pid, qty = ids[idx], X.extract_qty(q)
        v = self._call(ctx, "compliance_filter", state=s.last_state, product_ids=[pid])[0]      # re-check before acting
        if v["status"] != "ALLOWED":
            return "BLOCKED_ACTION", {"message": f"Cannot add {v['sku']}: {v['status']} ({v['reason_code']})."}
        basket = self._call(ctx, "add_to_basket_stub", product_id=pid, qty=qty)
        return "OK", {"basket": basket, "state": s.last_state}
