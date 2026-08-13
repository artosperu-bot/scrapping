from dataclasses import dataclass, field
from itertools import count


@dataclass
class ProcessSession:
    session_id: str
    kind: str
    label: str
    state: str = "running"
    product_percent: int = 0
    logs: list[str] = field(default_factory=list)


class ProcessRegistry:
    def __init__(self):
        self._ids = count(1)
        self._sessions = {}

    def start(self, kind, label, total=1):
        session = ProcessSession(f"{kind.lower()}-{next(self._ids):03d}", kind, label)
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id):
        return self._sessions.get(session_id)

    def apply(self, session_id, event):
        session = self._sessions[session_id]
        if event.get("product_percent") is not None:
            session.product_percent = max(0, min(100, int(event["product_percent"])))
        if event.get("type") in {"done", "batch_done"}:
            session.state = "complete"
            session.product_percent = 100
        elif event.get("type") in {"fatal", "error"}:
            session.state = "error"
        return session

    def log(self, session_id, message):
        self._sessions[session_id].logs.append(str(message))
