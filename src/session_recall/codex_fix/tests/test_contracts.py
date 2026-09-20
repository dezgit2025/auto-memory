"""Strict and canonical JSON contract tests."""

import pytest

from session_recall.codex_fix.contracts import (
    ContractError,
    canonical_bytes,
    digest,
    parse,
    validate,
)


SHA_A = "sha256:" + "a" * 64


def _selection(**changes):
    value = {
        "format_version": 1,
        "generation": 1,
        "artifact_digest": SHA_A,
        "source": "managed",
        "recipe_id": "reviewed-recipe",
        "activated_plan_digest": SHA_A,
    }
    value.update(changes)
    return value


def _journal(failure=None):
    selection = validate(_selection(), "Selection")
    return {
        "format_version": 1,
        "operation_id": "operation-1",
        "plan_digest": SHA_A,
        "phase": "failed" if failure is not None else "prepared",
        "prior_selection": None,
        "target_selection": selection,
        "started_at": "2026-09-20T00:00:00Z",
        "updated_at": "2026-09-20T00:00:01Z",
        "failure": failure,
    }


def test_parse_rejects_duplicate_keys():
    text = (
        '{"format_version":1,"known_recipe_mode":"explicit",'
        '"known_recipe_mode":"auto_opt_in","startup_trigger":"none",'
        '"allow_downloads":false}'
    )
    with pytest.raises(ContractError):
        parse(text, "ActivationPolicy")


def test_validate_rejects_unknown_and_missing_fields():
    policy = {
        "format_version": 1,
        "known_recipe_mode": "explicit",
        "startup_trigger": "none",
        "allow_downloads": False,
    }
    with pytest.raises(ContractError):
        validate({**policy, "surprise": True}, "ActivationPolicy")
    del policy["startup_trigger"]
    with pytest.raises(ContractError):
        validate(policy, "ActivationPolicy")


def test_validate_returns_the_original_validated_value():
    value = _selection()
    assert validate(value, "Selection") is value


@pytest.mark.parametrize("generation", [True, 1.0, -1, 2**63])
def test_integer_fields_reject_bool_float_and_out_of_range(generation):
    with pytest.raises(ContractError):
        validate(_selection(generation=generation), "Selection")
    assert validate(_selection(generation=2**63 - 1), "Selection")["generation"] == 2**63 - 1


def test_utf8_string_limit_counts_bytes():
    assert validate(_journal("é" * 256), "Journal")["failure"] == "é" * 256
    with pytest.raises(ContractError):
        validate(_journal("é" * 256 + "x"), "Journal")


def test_identifier_and_digest_syntax_are_strict():
    with pytest.raises(ContractError):
        validate(_selection(recipe_id="Uppercase"), "Selection")
    with pytest.raises(ContractError):
        validate(_selection(artifact_digest="sha256:" + "A" * 64), "Selection")


def test_collection_and_decoded_size_limits():
    recipe = {
        "recipe_id": "recipe-1",
        "source_adapter_digest": SHA_A,
        "schema_fingerprint": SHA_A,
        "target_artifact_digest": SHA_A,
        "check_ids": [f"check-{index}" for index in range(17)],
    }
    catalogue = {
        "format_version": 1,
        "catalogue_id": "catalogue-1",
        "seed_artifact_digest": SHA_A,
        "recipes": [recipe],
    }
    with pytest.raises(ContractError):
        validate(catalogue, "Catalogue")
    oversized = '{"format_version":1,"padding":"' + "x" * (2 * 1024 * 1024) + '"}'
    with pytest.raises(ContractError):
        parse(oversized, "ActivationPolicy")


def test_canonical_bytes_sort_objects_preserve_arrays_and_emit_utf8():
    left = {"é": [3, 2, 1], "a": {"z": 1, "b": 2}}
    right = {"a": {"b": 2, "z": 1}, "é": [3, 2, 1]}
    expected = b'{"a":{"b":2,"z":1},"\xc3\xa9":[3,2,1]}'
    assert canonical_bytes(left) == canonical_bytes(right) == expected
    assert digest(left) == digest(right)
    assert canonical_bytes({"a": [1, 2, 3]}) != canonical_bytes({"a": [3, 2, 1]})


def test_canonical_bytes_do_not_normalize_unicode():
    assert canonical_bytes({"value": "é"}) != canonical_bytes({"value": "e\u0301"})
    assert digest({"value": "é"}) != digest({"value": "e\u0301"})
