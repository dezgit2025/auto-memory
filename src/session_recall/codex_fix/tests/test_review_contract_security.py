"""Reviewer-requested contract and trusted-path regressions."""

from __future__ import annotations

from dataclasses import replace

import pytest

import session_recall.codex_fix.contracts as contracts
from session_recall.codex_fix.contracts import ContractError, parse, validate
from session_recall.codex_fix.engine import plan


def test_plan_rejects_unknown_but_well_formed_check_id(engine_case_factory):
    case = engine_case_factory()
    value = {**plan(case.classification, case.context)}
    value["check_ids"] = ["valid-but-unknown"]
    with pytest.raises(ContractError):
        validate(value, "Plan")


def test_deep_json_is_contract_error_not_python_recursion_error():
    deeply_nested = "[" * 1_100 + "0" + "]" * 1_100
    with pytest.raises(ContractError):
        parse(deeply_nested, "ActivationPolicy")


def test_decoder_recursion_error_is_mapped_to_invalid_json(monkeypatch):
    def recursive_decoder(*_args, **_kwargs):
        raise RecursionError("decoder nesting limit")

    monkeypatch.setattr(contracts.json, "loads", recursive_decoder)
    with pytest.raises(ContractError) as raised:
        contracts.parse("[]", "ActivationPolicy")
    assert raised.value.code == "invalid_json"


def test_context_copies_caller_owned_paths(engine_case_factory, tmp_path):
    case = engine_case_factory()
    original_selection = case.context.paths["current_selection"]
    caller_paths = dict(case.context.paths)
    isolated = replace(case.context, paths=caller_paths)
    caller_paths["current_selection"] = tmp_path / "redirected.json"
    assert isolated.paths["current_selection"] == original_selection


def test_context_rejects_selection_outside_managed_root(
    engine_case_factory, tmp_path
):
    case = engine_case_factory()
    paths = {
        **case.context.paths,
        "current_selection": tmp_path / "outside" / "current.json",
    }
    with pytest.raises(ContractError) as raised:
        replace(case.context, paths=paths)
    assert raised.value.code == "invalid_context"


def test_context_rejects_symlink_parent_for_selection(engine_case_factory, tmp_path):
    case = engine_case_factory()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = case.context.managed_root / "selection-link"
    link.symlink_to(outside, target_is_directory=True)
    paths = {**case.context.paths, "current_selection": link / "current.json"}
    with pytest.raises(ContractError) as raised:
        replace(case.context, paths=paths)
    assert raised.value.code == "invalid_context"
