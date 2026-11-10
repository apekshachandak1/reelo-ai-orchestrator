"""LAYER: ORCHESTRATOR / PIPELINE.  request -> route -> plan -> authorize -> execute -> validate -> format -> persist."""
from dataclasses import dataclass, field
from typing import Any, Optional
from .execution.chains import Chains
from .output.formatter import format_answer
from .observability.observability import Trace
from .routing.planner import make_plan
from .safety.policy import ALLOWLIST
from .routing.router import classify
from .execution.runner import PermissionDenied, ToolRunner
from .state.state import Session, SessionStore
from .safety.validator import validate_invariants


@dataclass
class Ctx:
    req: dict
    user_type: str
    sid: str
    query: str
    trace: Trace
    sess: Session
    route: Optional[Any] = None
    plan: Optional[Any] = None
    status: Optional[str] = None
    payload: Any = None
    updates: dict = field(default_factory=dict)
    answer: str = ""
    response: Optional[dict] = None


class Orchestrator:
    def __init__(self):
        self.sessions, self.runner = SessionStore(), ToolRunner()
        self.chains = Chains(self.runner)

    def n_route(self, ctx):
        ctx.route = classify(ctx.query)
        ctx.plan = make_plan(ctx.route)
        ctx.trace.intent, ctx.trace.lane = ctx.route.intent, ctx.route.lane
        return ctx

    def n_authorize(self, ctx):
        """Fail fast: if ANY tool in the planned chain is off-limits, run NOTHING."""
        missing = [t for t in ctx.plan.tools if t not in ALLOWLIST[ctx.user_type]]
        if missing:
            for t in missing:
                ctx.trace.denied.append({"tool": t, "stage": "plan"})
                ctx.trace.audit_event(t, False, {"stage": "plan"})
            ctx.status = "DENIED"
            ctx.payload = {"message": f"Permission denied: '{ctx.user_type}' cannot use {', '.join(missing)}."}
        return ctx

    def n_execute(self, ctx):
        c = self.chains
        handler = c.basket if ctx.route.action == "ADD_TO_BASKET" else {
            "SALES_RECO": c.sales, "COMPLIANCE_CHECK": c.compliance, "OPS_STOCK": c.stock,
            "VENDOR_ONBOARDING": c.vendor, "GENERAL_KB": c.kb}[ctx.route.intent]
        try:
            ctx.status, ctx.payload = handler(ctx)
        except PermissionDenied as e:
            ctx.status, ctx.payload = "DENIED", {"message": f"Permission denied: {e}."}
        return ctx

    def n_validate(self, ctx):
        problems = validate_invariants(ctx)
        if problems:
            ctx.trace.validation += problems
            ctx.status, ctx.payload, ctx.updates = "ERROR", {"message": "Internal consistency check failed; result withheld."}, {}
        return ctx

    def n_format(self, ctx):
        ctx.answer = format_answer(ctx.route.intent, ctx.status, ctx.payload, ctx.query, ctx.trace, ctx.route.action)
        return ctx

    def n_persist(self, ctx):
        if ctx.status == "OK":                                      # memory written only after validation passes
            ctx.sess.apply({**ctx.updates, "last_intent": ctx.route.intent})
        rec = ctx.trace.finish(ctx.status)
        ctx.response = {
            "request_id": ctx.trace.request_id, "intent": ctx.route.intent, "user_type": ctx.user_type,
            "status": ctx.status, "answer": ctx.answer, "data": ctx.payload, "session": ctx.sess.snapshot(),
            "meta": {"planned_chain": ctx.plan.tools, "latency_ms_total": rec["latency_ms_total"],
                     "tools_called": [(t["tool"], t["latency_ms"]) for t in rec["tools_called"]],
                     "prompt_tokens_est": rec["prompt_tokens_est"]}}
        return ctx

    def handle(self, req):
        user_type, sid = req.get("user_type", "portal_customer"), req.get("session_id", "default")   # least privilege default
        if user_type not in ALLOWLIST or not isinstance(req.get("query"), str) or not req["query"].strip():
            return {"status": "INVALID_INPUT", "answer": "Need a non-empty 'query' and a valid 'user_type'."}
        ctx = Ctx(req, user_type, sid, req["query"], Trace(user_type, sid, req["query"]), self.sessions.get(sid))
        ctx = self.n_authorize(self.n_route(ctx))
        if ctx.status is None:
            ctx = self.n_validate(self.n_execute(ctx))
        return self.n_persist(self.n_format(ctx)).response
