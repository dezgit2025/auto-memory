"""Deterministic recipe classification and planning tests."""

import subprocess
import sys
import textwrap

import pytest

from session_recall.codex_fix.contracts import ContractError, canonical_bytes, digest
from session_recall.codex_fix.engine import plan

from .conftest import CHECK_IDS, SOURCE_DIGEST, TARGET_DIGEST


def test_exact_known_recipe_has_canonical_manifest_and_provenance(engine_case_factory):
    first = engine_case_factory()
    second = engine_case_factory()
    first_plan = plan(first.classification, first.context)
    second_plan = plan(second.classification, second.context)

    assert first.classification == {
        "format_version": 1,
        "status": "known_repair",
        "observation_digest": first.observation["input_fingerprint"],
        "recipe_id": "codex-state52-artifact-to-state55-v1",
        "reason_code": None,
    }
    expected_input = {
        "schema_fingerprint": first.observation["snapshot"]["schema_fingerprint"],
        "adapter": first.identity,
        "catalogue_digest": digest(first.catalogue),
        "policy_digest": digest(first.policy),
    }
    assert first.observation["input_fingerprint"] == digest(expected_input)
    assert canonical_bytes(first_plan) == canonical_bytes(second_plan)
    assert first_plan == second_plan
    assert first_plan["input_fingerprint"] == first.observation["input_fingerprint"]
    assert first_plan["source_adapter_digest"] == SOURCE_DIGEST
    assert first_plan["target_artifact_digest"] == TARGET_DIGEST
    assert first_plan["catalogue_digest"] == digest(first.catalogue)
    assert first_plan["policy_digest"] == digest(first.policy)
    assert first_plan["check_ids"] == CHECK_IDS
    assert first_plan["prior_selection_digest"] == digest(first.selection)
    assert first_plan["activation"] == "explicit_apply"


def test_persisted_auto_policy_only_changes_manifest_activation(engine_case_factory):
    case = engine_case_factory(policy_mode="auto_opt_in")
    repair_plan = plan(case.classification, case.context)
    assert repair_plan["activation"] == "opted_in_known_auto"
    assert case.context.paths["current_selection"].read_bytes() == canonical_bytes(
        case.selection
    )


@pytest.mark.parametrize(
    ("route", "status", "code"),
    [
        ("unknown", "assistance_eligible", "no_recipe"),
        ("ambiguous", "ambiguous_recipe", "ambiguous_recipe"),
    ],
)
def test_unknown_and_ambiguous_routes_refuse_planning(
    engine_case_factory, route, status, code
):
    case = engine_case_factory(route)
    assert case.classification["status"] == status
    assert case.classification["recipe_id"] is None
    assert case.classification["reason_code"] == code
    with pytest.raises(ContractError) as raised:
        plan(case.classification, case.context)
    assert raised.value.code == code


def test_legacy_install_is_diagnosis_only(engine_case_factory):
    case = engine_case_factory(adapter_kind="legacy")
    assert case.classification["status"] == "unmanaged_legacy"
    assert case.classification["recipe_id"] is None
    assert case.classification["reason_code"] == "unmanaged_legacy"
    with pytest.raises(ContractError) as raised:
        plan(case.classification, case.context)
    assert raised.value.code == "unmanaged_legacy"


def test_core_imports_are_independent_in_fresh_interpreter():
    script = textwrap.dedent(
        """
        import importlib.abc
        import sys

        class DenyForbidden(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                forbidden = (
                    "session_recall.providers.codex",
                    "session_recall.codex_fix.transport",
                )
                if fullname.startswith(forbidden):
                    raise RuntimeError(f"forbidden import: {fullname}")
                return None

        sys.meta_path.insert(0, DenyForbidden())
        import session_recall.codex_metadata
        import session_recall.codex_fix.context
        import session_recall.codex_fix.contracts
        import session_recall.codex_fix.engine
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
