"""Tiny output helper for the Codex CLI (reuses the shared JSON formatter)."""

from ...util.format_output import fmt_json


def dump_json(obj) -> None:
    print(fmt_json(obj))
