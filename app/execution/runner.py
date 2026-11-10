"""LAYER: TOOL RUNNER. The ONE gate every tool call passes through:
allowlist -> execute -> timing/trace -> audit log."""
from . import tools as T
from ..safety.policy import ALLOWLIST


class PermissionDenied(Exception):
    pass


class ToolRunner:
    def call(self, trace, user_type, name, **kw):
        if name not in ALLOWLIST[user_type]:                       # enforced at call time too
            trace.denied.append({"tool": name, "args": kw})
            trace.audit_event(name, False, kw)
            raise PermissionDenied(f"'{user_type}' is not allowed to use '{name}'")
        with trace.tool(name, kw) as rec:
            out = T.TOOLS[name](**kw)
            rec["output"] = out
        trace.audit_event(name, True, kw, out)
        return out
