"""AllBackend — fans out queries to every available backend and merges results."""
from __future__ import annotations
import importlib
import sys
from typing import Optional

from .base import SessionBackend


# (backend_name, module_path, class_name) — order controls precedence for dedup/show.
_BACKEND_SPECS = [
    ("copilot", ".copilot",     "CopilotBackend"),
    ("claude",  ".claude_code", "ClaudeCodeBackend"),
    ("aider",   ".aider",       "AiderBackend"),
    ("cursor",  ".cursor",      "CursorBackend"),
]


def _warn(backend_name: str, op: str, err: Exception) -> None:
    print(f"warning: {backend_name} backend error in {op} — {err}", file=sys.stderr)


class AllBackend(SessionBackend):
    """Query all available backends and merge results."""

    def __init__(self) -> None:
        self._backends: list[SessionBackend] = []
        for _name, mod_path, cls_name in _BACKEND_SPECS:
            try:
                mod = importlib.import_module(mod_path, package=__package__)
                b = getattr(mod, cls_name)()
                if b.is_available():
                    self._backends.append(b)
            except ImportError:
                pass
            except Exception as e:
                print(f"warning: {cls_name} failed to initialise — skipping. {e}", file=sys.stderr)

    @property
    def name(self) -> str:
        return "all"

    def is_available(self) -> bool:
        return bool(self._backends)

    def _fanout(self, op: str, key_fn, call):
        """Run `call(backend)` across backends, dedup by `key_fn(item)`, tag with _backend."""
        seen: set[str] = set()
        merged: list[dict] = []
        for b in self._backends:
            try:
                for item in call(b):
                    key = key_fn(item)
                    if key in seen:
                        continue
                    seen.add(key)
                    item["_backend"] = b.name
                    merged.append(item)
            except Exception as e:
                _warn(b.name, op, e)
        return merged

    def list_sessions(self, *, repo=None, limit=10, days=30) -> list[dict]:
        merged = self._fanout(
            "list_sessions",
            _session_key,
            lambda b: b.list_sessions(repo=repo, limit=limit, days=days),
        )
        merged.sort(key=lambda s: s.get("created_at") or s.get("date") or "", reverse=True)
        return merged[:limit]

    def list_files(self, *, repo=None, limit=20, days=30) -> list[dict]:
        merged = self._fanout(
            "list_files",
            lambda f: f.get("file_path", ""),
            lambda b: b.list_files(repo=repo, limit=limit, days=days),
        )
        merged.sort(key=lambda f: f.get("date") or "", reverse=True)
        return merged[:limit]

    def search(self, query: str, *, repo=None, limit=10, days=30) -> list[dict]:
        merged = self._fanout(
            "search",
            lambda r: r.get("session_id", "") + r.get("source_type", ""),
            lambda b: b.search(query, repo=repo, limit=limit, days=days),
        )
        return merged[:limit]

    def show_session(self, session_id: str, *, turns=None) -> Optional[dict]:
        for b in self._backends:
            try:
                result = b.show_session(session_id, turns=turns)
                if result:
                    result["_backend"] = b.name
                    return result
            except Exception as e:
                _warn(b.name, "show_session", e)
        return None

    def health(self) -> dict:
        all_dims: list[dict] = []
        per_backend: list[dict] = []
        for b in self._backends:
            try:
                h = b.health()
                for d in h.get("dimensions", []):
                    d["_backend"] = b.name
                    all_dims.append(d)
                per_backend.append({
                    "backend": b.name,
                    "score": h.get("score", 0.0),
                    "zone": h.get("zone", "RED"),
                })
            except Exception as e:
                _warn(b.name, "health", e)
                per_backend.append({"backend": b.name, "score": 0.0, "zone": "RED"})

        # Use minimum score — zone reflects the weakest backend.
        scores = [x["score"] for x in per_backend]
        score = round(min(scores), 1) if scores else 0.0
        if score < 5:
            zone = "RED"
        elif score < 8:
            zone = "AMBER"
        else:
            zone = "GREEN"
        return {"score": score, "zone": zone, "backends": per_backend, "dimensions": all_dims}


def _session_key(s: dict) -> str:
    """Deduplicate by (repository, summary prefix, date). Lossy by design."""
    repo = s.get("repository", "")
    summary = (s.get("summary") or "")[:40]
    date = (s.get("created_at") or s.get("date") or "")[:10]
    return f"{repo}|{summary}|{date}"
