"""Exact local-only ControllerConfig envelope validation."""

from __future__ import annotations

from typing import Any

from ._contract_schema import _policy, _version, obj, string


FIELDS = {
    "format_version",
    "root",
    "state_db",
    "history_db",
    "sessions_root",
    "activation_policy",
}


def controller_config(value: Any) -> None:
    value = obj(value, FIELDS, "ControllerConfig")
    _version(value, "ControllerConfig")
    for name in ("root", "state_db", "history_db", "sessions_root"):
        item = value[name]
        if item is not None:
            string(item, f"ControllerConfig.{name}", maximum=4096)
            if not item or "\x00" in item:
                from .contracts import ContractError

                raise ContractError("invalid_contract", f"ControllerConfig.{name} is invalid")
    _policy(value["activation_policy"])
