"""AllBackend — fans out queries to every available backend and merges results."""
from __future__ import annotations
import sys
from typing import Optional
from .base import SessionBackend


class AllBackend(SessionBackend):
    """Query all available backends and merge results."""

    def __init__(self) -> None:
        self._backends: list[SessionBackend] = []
        self._load()

    def _load(self) -> None:
        for _name, _mod, _cls in [
            ("copilot", ".copilot", "CopilotBackend"),
            ("claude",  ".claude_code", "ClaudeCodeBackend"),
            ("aider",   ".aider",  "AiderBackend"),
            ("cursor",  ".cursor", "CursorBackend"),
        ]:
            try:
                import importlib
                mod = importlib.import_module(_mod, package=__package__)
                cls = getattr(mod, _cls)
                b = cls()
                if b.is_available():
                    self._backends.append(b)
            except ImportError:
                pass
            except Exception as e:
                print(f"warning: {_cls} failed to initialise — skipping. {e}", file=sys.stderr)

    @property
    def name(self) -> str:
        return "all"

    def is_available(self) -> bool:
        return bool(self._backends)

    def list_sessions(self, *, repo=None, limit=10, days=30) -> list[dict]:
        seen: set[str] = set()
        merged = []
        for b in self._backends:
            try:
                for s in b.list_sessions(repo=repo, limit=limit, days=days):
                    key = _session_key(s)
                    if key not in seen:
                        seen.add(key)
                        s["_backend"] = b.name
                        merged.append(s)
            except Exception as e:
                print(f"warning: {b.name} backend error in list_sessions — {e}", file=sys.stderr)
        merged.sort(key=lambda s: s.get("created_at") or s.get("date") or "", reverse=True)
        return merged[:limit]

    def list_files(self, *, repo=None, limit=20, days=30) -> list[dict]:
        seen: set[str] = set()
        merged = []
        for b in self._backends:
            try:
                for f in b.list_files(repo=repo, limit=limit, days=days):
                    key = f.get("file_path", "")
                    if key not in seen:
                        seen.add(key)
                        f["_backend"] = b.name
                        merged.append(f)
            except Exception as e:
                print(f"warning: {b.name} backend error in list_files — {e}", file=sys.stderr)
        merged.sort(key=lambda f: f.get("date") or "", reverse=True)
        return merged[:limit]

    def search(self, query: str, *, repo=None, limit=10, days=30) -> list[dict]:
        seen: set[str] = set()
        merged = []
        for b in self._backends:
            try:
                for r in b.search(query, repo=repo, limit=limit, days=days):
                    key = r.get("session_id", "") + r.get("source_type", "")
                    if key not in seen:
                        seen.add(key)
                        r["_backend"] = b.name
                        merged.append(r)
            except Exception as e:
                print(f"warning: {b.name} backend error in search — {e}", file=sys.stderr)
        return merged[:limit]

    def show_session(self, session_id: str, *, turns=None) -> Optional[dict]:
        for b in self._backends:
            try:
                result = b.show_session(session_id, turns=turns)
                if result:
                    result["_backend"] = b.name
                    return result
            except Exception as e:
                print(f"warning: {b.name} backend error in show_session — {e}", file=sys.stderr)
        return None

    def health(self) -> dict:
        all_dims = []
        per_backend = []
        for b in self._backends:
            try:
                h = b.health()
                for d in h.get("dimensions", []):
                    d["_backend"] = b.name
                    all_dims.append(d)
                per_backend.append({"backend": b.name, "score": h.get("score", 0.0),
                                    "zone": h.get("zone", "RED")})
            except Exception as e:
                print(f"warning: {b.name} backend error in health — {e}", file=sys.stderr)
                per_backend.append({"backend": b.name, "score": 0.0, "zone": "RED"})
        # Use minimum score — zone reflects the weakest backend
        scores = [x["score"] for x in per_backend]
        score = round(min(scores), 1) if scores else 0.0
        zone = "RED" if score < 5 else ("AMBER" if score < 8 else "GREEN")
        return {"score": score, "zone": zone,
                "backends": per_backend, "dimensions": all_dims}


def _session_key(s: dict) -> str:
    """Deduplicate by (repository, summary prefix, date). Lossy by design."""
    repo = s.get("repository", "")
    summary = (s.get("summary") or "")[:40]
    date = (s.get("created_at") or s.get("date") or "")[:10]
    return f"{repo}|{summary}|{date}"
