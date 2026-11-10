"""One entry point:  python main.py        runs the live-demo prompts (add `chat [user_type]` for interactive)."""
import sys
from app.execution import tools as T
from app.engine import Orchestrator


def demo(o):
    d = T.data()
    blocked = next((p for p in d["products"] if "CA" in p["blocked_states"]), d["products"][0])
    stocked = next(p for p in d["products"] if d["inv"].get(p["product_id"]))
    steps = [
        ("internal_sales", "s1", "Give me hot picks for CA under $5000"),
        ("internal_sales", "s1", "Ok add 2 of the first one to the basket"),                 # memory follow-up
        ("internal_sales", "s2", f"Why is {blocked['sku']} not available in CA? Suggest alternatives."),
        ("internal_sales", "s2", f"How much stock does {stocked['sku']} have and where?"),
        ("portal_vendor", "s3", "I'm uploading a product missing Net Wt and no lab report - what do I fix?"),
        ("portal_customer", "s4", f"How much stock does {stocked['sku']} have?"),            # DENIED by allowlist
    ]
    for ut, sid, q in steps:
        r = o.handle({"user_type": ut, "session_id": sid, "query": q})
        print(f"\n[{ut}] {q}\n -> intent={r['intent']} status={r['status']} tools={[t[0] for t in r['meta']['tools_called']]}\n{r['answer']}")
    print("\nlogs: logs/traces.jsonl, logs/audit.jsonl")


def chat(o, ut="internal_sales"):
    while (q := input("\nyou> ").strip()):
        r = o.handle({"user_type": ut, "session_id": "cli", "query": q})
        print(f"[{r['intent']}/{r['status']}] {r['answer']}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "demo"
    o = Orchestrator()
    chat(o, *sys.argv[2:3]) if cmd == "chat" else demo(o)
