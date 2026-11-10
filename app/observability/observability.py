"""LAYER: OBSERVABILITY. One JSON line per request (traces.jsonl) + one line per tool call (audit.jsonl).
Production: same shapes shipped to an append-only audit store / Langfuse."""
import hashlib, json, os, sys, time, uuid
from contextlib import contextmanager
from pathlib import Path
from ..safety.pii import redact, redact_obj

LOG_DIR = Path(os.getenv("LOG_DIR", Path(__file__).resolve().parent.parent.parent / "logs"))


def digest(obj) -> str:
    """Output hash: tamper-evident audit without storing the payload."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _append(name, record):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_DIR / name, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


class Trace:
    def __init__(self, user_type, session_id, query):
        self.request_id = uuid.uuid4().hex[:12]
        self.user_type, self.session_id, self.query = user_type, session_id, redact(query)
        self.intent = self.lane = None
        self.tools, self.denied, self.outputs, self.validation = [], [], [], []
        self.prompt_tokens_est = 0
        self._t0 = time.perf_counter()

    @contextmanager
    def tool(self, name, args):
        rec, s = {"tool": name, "args": redact_obj(args)}, time.perf_counter()
        try:
            yield rec
        except Exception as e:
            rec["error"] = repr(e)
            raise
        finally:
            rec["latency_ms"] = round((time.perf_counter() - s) * 1000, 3)
            if "output" in rec:
                self.outputs.append((name, args, rec["output"]))      # kept in memory for the validator only
                rec["output_hash"] = digest(rec.pop("output"))
            self.tools.append(rec)

    def audit_event(self, tool, allowed, args, output=None):
        _append("audit.jsonl", {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "request_id": self.request_id,
                                "user_type": self.user_type, "tool": tool, "allowed": allowed,
                                "args_hash": digest(args), "output_hash": digest(output) if output is not None else None})

    def finish(self, status):
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "request_id": self.request_id, "session_id": self.session_id,
                  "user_type": self.user_type, "intent": self.intent, "lane": self.lane, "status": status,
                  "query": self.query, "tools_called": self.tools, "denied_tools": self.denied,
                  "validation_failures": self.validation,
                  "latency_ms_total": round((time.perf_counter() - self._t0) * 1000, 3),
                  "prompt_tokens_est": self.prompt_tokens_est}
        _append("traces.jsonl", record)
        if os.getenv("LOG_STDERR", "1") == "1":
            print("TRACE " + json.dumps(record, default=str), file=sys.stderr)
        return record
