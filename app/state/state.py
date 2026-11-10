"""LAYER: STATE. Per-session memory. In-memory dict for the PoC.
Production: Redis hash `session:{id}` with a TTL so every orchestrator pod shares it."""
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional

SESSION_TTL = 1800


@dataclass
class Session:
    last_intent: Optional[str] = None
    last_state: Optional[str] = None
    last_budget: Optional[float] = None
    last_product_ids: list = field(default_factory=list)
    touched: float = field(default_factory=time.monotonic, repr=False)

    def snapshot(self):
        d = asdict(self)
        d.pop("touched")
        return d

    def apply(self, updates: dict):
        for k, v in updates.items():
            setattr(self, k, v)
        self.touched = time.monotonic()


class SessionStore:
    def __init__(self):
        self._s: Dict[str, Session] = {}

    def get(self, sid):
        now = time.monotonic()
        for k in [k for k, s in self._s.items() if now - s.touched > SESSION_TTL]:
            del self._s[k]
        return self._s.setdefault(sid, Session())
