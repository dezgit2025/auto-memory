"""AllBackend — fans out queries to every available backend and merges results."""
from __future__ import annotations
from typing import Optional
from .base import SessionBackend


class AllBackend(SessionBackend):
    """Query all available backends and merge results."""

    def __init__(self) -> None:
        self._backends: list[SessionBackend] = []
        self._load()

    def _load(self) -> None:
        from .copilot import CopilotBackend
        b = CopilotBackend()
        if b.is_available():
            self._backends.append(b)
        try:
            from .claude_code import ClaudeCodeBackend
            b2 = ClaudeCodeBackend()
            if b2.is_available():
                self._backends.append(b2)
        except ImportError:
            pass

    @property
    def name(self) -> str:
        return "all"

    def is_available(self) -> bool:
        return bool(self._backends)

    def list_sessions(self, *, repo=None, limit=10, days=30) -> list[dict]:
        seen: set[str] = set()
        merged = []
        for b in self._backends:
            for s in b.list_sessions(repo=repo, limit=limit, days=days):
                key = _session_key(s)
                if key not in seen:
                    seen.add(key)
                    s["_backend"] = b.name
                    merged.append(s)
        merged.sort(key=lambda s: s.get("created_at") or s.get("date") or "", reverse=True)
        return merged[:limit]

    def list_files(self, *, repo=None, limit=20, days=30) -> list[dict]:
        seen: set[str] = set()
        merged = []
        for b in self._backends:
            for f in b.list_files(repo=repo, limit=limit, days=days):
                key = f.get("file_path", "")
                if key not in seen:
                    seen.add(key)
                    f["_backend"] = b.name
                    merged.append(f)
        merged.sort(key=lambda f: f.get("date") or "", reverse=True)
        return merged[:limit]

    def search(self, query: str, *, repo=None, limit=10, days=30) -> list[dict]:
        seen: set[str] = set()
        merged = []
        for b in self._backends:
            for r in b.search(query, repo=repo, limit=limit, days=days):
                key = r.get("session_id", "") + r.get("source_type", "")
                if key not in seen:
                    seen.add(key)
                    r["_backend"] = b.name
                    merged.append(r)
        return merged[:limit]

    def show_session(self, session_id: str, *, turns=None) -> Optional[dict]:
        # show is backend-scoped — try each backend until one returns a result
        for b in self._backends:
            result = b.show_session(session_id, turns=turns)
            if result:
                result["_backend"] = b.name
                return result
        return None

    def health(self) -> dict:
        all_dims = []
        scores = []
        for b in self._backends:
            h = b.health()
            for d in h.get("dimensions", []):
                d["_backend"] = b.name
                all_dims.append(d)
            scores.append(h.get("score", 0.0))
        avg = round(sum(scores) / len(scores), 1) if scores else 0.0
        zone = "GREEN" if avg >= 8 else ("AMBER" if avg >= 5 else "RED")
        return {"score": avg, "zone": zone, "backends": [b.name for b in self._backends], "dimensions": all_dims}


def _session_key(s: dict) -> str:
    """Deduplicate sessions by (repository, summary prefix, date)."""
    repo = s.get("repository", "")
    summary = (s.get("summary") or "")[:40]
    date = (s.get("created_at") or s.get("date") or "")[:10]
    return f"{repo}|{summary}|{date}"
