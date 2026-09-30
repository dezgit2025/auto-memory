"""Declarative validation rules for v1 Codex fixer envelopes."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Callable


ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_INT = 2**63 - 1
CONTROLLER_CHECK_IDS = {
    "artifact_manifest_v1",
    "synthetic_schema_v1",
    "trial_cli_contract_v1",
    "unknown_drift_rejected_v1",
    "synthetic_no_write_v1",
}


def _fail(message: str) -> None:
    from .contracts import ContractError

    raise ContractError("invalid_contract", message)


def obj(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(f"{label} must contain exactly {sorted(fields)!r}")
    if any(not isinstance(key, str) for key in value):
        _fail(f"{label} keys must be strings")
    return value


def integer(value: Any, label: str, *, maximum: int = MAX_INT, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(f"{label} must be an integer in {minimum}..{maximum}")
    return value


def boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        _fail(f"{label} must be a boolean")
    return value


def string(value: Any, label: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or len(value.encode("utf-8")) > maximum:
        _fail(f"{label} must be a UTF-8 string of at most {maximum} bytes")
    return value


def enum(value: Any, allowed: set[str], label: str) -> str:
    string(value, label)
    if value not in allowed:
        _fail(f"{label} has an unsupported value")
    return value


def identifier(value: Any, label: str) -> str:
    string(value, label, maximum=64)
    if ID_RE.fullmatch(value) is None:
        _fail(f"{label} is not a valid identifier")
    return value


def digest_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        _fail(f"{label} is not a sha256 digest")
    return value


def array(value: Any, label: str, *, minimum: int = 0, maximum: int) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        _fail(f"{label} must contain {minimum}..{maximum} items")
    return value


def ids(value: Any, label: str, *, minimum: int = 0, maximum: int = 16) -> list[str]:
    result = array(value, label, minimum=minimum, maximum=maximum)
    for index, item in enumerate(result):
        identifier(item, f"{label}[{index}]")
    if len(set(result)) != len(result):
        _fail(f"{label} contains duplicates")
    return result


def relative_path(value: Any, label: str) -> str:
    string(value, label, maximum=4096)
    path = PurePosixPath(value)
    if not value or path.is_absolute() or "\\" in value or ".." in path.parts:
        _fail(f"{label} must be a normalized relative POSIX path")
    if value != path.as_posix() or value in {".", ""}:
        _fail(f"{label} must be normalized")
    return value


def _version(value: dict[str, Any], label: str) -> None:
    if integer(value["format_version"], f"{label}.format_version") != 1:
        _fail(f"{label}.format_version must be 1")


def column(value: Any) -> None:
    value = obj(value, {"cid", "name", "declared_type", "not_null", "default_sql", "pk_position"}, "Column")
    integer(value["cid"], "Column.cid", maximum=255)
    string(value["name"], "Column.name", maximum=128)
    string(value["declared_type"], "Column.declared_type", maximum=128)
    boolean(value["not_null"], "Column.not_null")
    if value["default_sql"] is not None:
        string(value["default_sql"], "Column.default_sql")
    integer(value["pk_position"], "Column.pk_position", maximum=32)


def table(value: Any) -> None:
    value = obj(value, {"name", "columns"}, "Table")
    string(value["name"], "Table.name", maximum=128)
    for item in array(value["columns"], "Table.columns", maximum=256):
        column(item)


def profile(value: Any) -> None:
    value = obj(value, {"filename", "migration_ceiling", "failed_migrations", "json1", "tables"}, "UsedProfile")
    string(value["filename"], "UsedProfile.filename", maximum=128)
    integer(value["migration_ceiling"], "UsedProfile.migration_ceiling", maximum=1_000_000)
    integer(value["failed_migrations"], "UsedProfile.failed_migrations", maximum=1_000_000)
    boolean(value["json1"], "UsedProfile.json1")
    tables = array(value["tables"], "UsedProfile.tables", maximum=4)
    for item in tables:
        table(item)
    names = [item["name"] for item in tables]
    if len(set(names)) != len(names):
        _fail("UsedProfile.tables contains duplicate names")


def adapter(value: Any) -> None:
    value = obj(value, {"kind", "artifact_digest", "profile_id"}, "AdapterIdentity")
    enum(value["kind"], {"managed", "bundled", "legacy"}, "AdapterIdentity.kind")
    if value["artifact_digest"] is not None:
        digest_value(value["artifact_digest"], "AdapterIdentity.artifact_digest")
    if value["profile_id"] is not None:
        identifier(value["profile_id"], "AdapterIdentity.profile_id")


def recipe(value: Any) -> None:
    value = obj(value, {"recipe_id", "source_adapter_digest", "schema_fingerprint", "target_artifact_digest", "check_ids"}, "Recipe")
    identifier(value["recipe_id"], "Recipe.recipe_id")
    for name in ("source_adapter_digest", "schema_fingerprint", "target_artifact_digest"):
        digest_value(value[name], f"Recipe.{name}")
    check_ids = ids(value["check_ids"], "Recipe.check_ids", minimum=1)
    if not set(check_ids) <= CONTROLLER_CHECK_IDS:
        _fail("Recipe.check_ids contains an unknown controller check")


def selection(value: Any) -> None:
    value = obj(value, {"format_version", "generation", "artifact_digest", "source", "recipe_id", "activated_plan_digest"}, "Selection")
    _version(value, "Selection")
    integer(value["generation"], "Selection.generation")
    digest_value(value["artifact_digest"], "Selection.artifact_digest")
    enum(value["source"], {"bundled", "managed"}, "Selection.source")
    identifier(value["recipe_id"], "Selection.recipe_id")
    digest_value(value["activated_plan_digest"], "Selection.activated_plan_digest")


def source(value: Any) -> None:
    value = obj(value, {"path", "sha256", "content"}, "Source")
    relative_path(value["path"], "Source.path")
    digest_value(value["sha256"], "Source.sha256")
    string(value["content"], "Source.content", maximum=256 * 1024)


def _snapshot(value: Any) -> None:
    value = obj(value, {"format_version", "storage_family", "state", "history", "schema_fingerprint", "diagnostics"}, "SchemaSnapshot")
    _version(value, "SchemaSnapshot")
    identifier(value["storage_family"], "SchemaSnapshot.storage_family")
    profile(value["state"])
    profile(value["history"])
    if [item["name"] for item in value["state"]["tables"]] != ["threads", "_sqlx_migrations"]:
        _fail("SchemaSnapshot.state has unexpected used tables")
    if [item["name"] for item in value["history"]["tables"]] != ["thread_items", "thread_turns", "_sqlx_migrations"]:
        _fail("SchemaSnapshot.history has unexpected used tables")
    digest_value(value["schema_fingerprint"], "SchemaSnapshot.schema_fingerprint")
    for item in array(value["diagnostics"], "SchemaSnapshot.diagnostics", maximum=128):
        string(item, "SchemaSnapshot.diagnostics item")


def _observation(value: Any) -> None:
    value = obj(value, {"format_version", "snapshot", "adapter", "catalogue_digest", "policy_digest", "input_fingerprint"}, "Observation")
    _version(value, "Observation")
    _snapshot(value["snapshot"])
    adapter(value["adapter"])
    for name in ("catalogue_digest", "policy_digest", "input_fingerprint"):
        digest_value(value[name], f"Observation.{name}")


def _classification(value: Any) -> None:
    value = obj(value, {"format_version", "status", "observation_digest", "recipe_id", "reason_code"}, "Classification")
    _version(value, "Classification")
    enum(value["status"], {"supported", "known_repair", "assistance_eligible", "unmanaged_legacy", "ambiguous_recipe", "invalid"}, "Classification.status")
    digest_value(value["observation_digest"], "Classification.observation_digest")
    for name in ("recipe_id", "reason_code"):
        if value[name] is not None:
            identifier(value[name], f"Classification.{name}")


def _catalogue(value: Any) -> None:
    value = obj(value, {"format_version", "catalogue_id", "seed_artifact_digest", "recipes"}, "Catalogue")
    _version(value, "Catalogue")
    identifier(value["catalogue_id"], "Catalogue.catalogue_id")
    digest_value(value["seed_artifact_digest"], "Catalogue.seed_artifact_digest")
    recipes = array(value["recipes"], "Catalogue.recipes", maximum=128)
    for item in recipes:
        recipe(item)
    recipe_ids = [item["recipe_id"] for item in recipes]
    if len(recipe_ids) != len(set(recipe_ids)):
        _fail("Catalogue.recipes contains duplicate recipe IDs")


def _plan(value: Any) -> None:
    fields = {"format_version", "kind", "input_fingerprint", "source_adapter_digest", "catalogue_digest", "policy_digest", "recipe_id", "target_artifact_digest", "check_ids", "prior_selection_digest", "activation"}
    value = obj(value, fields, "Plan")
    _version(value, "Plan")
    enum(value["kind"], {"reviewed_recipe"}, "Plan.kind")
    for name in ("input_fingerprint", "source_adapter_digest", "catalogue_digest", "policy_digest", "target_artifact_digest"):
        digest_value(value[name], f"Plan.{name}")
    identifier(value["recipe_id"], "Plan.recipe_id")
    check_ids = ids(value["check_ids"], "Plan.check_ids", minimum=1)
    if not set(check_ids) <= CONTROLLER_CHECK_IDS:
        _fail("Plan.check_ids contains an unknown controller check")
    if value["prior_selection_digest"] is not None:
        digest_value(value["prior_selection_digest"], "Plan.prior_selection_digest")
    enum(value["activation"], {"explicit_apply", "opted_in_known_auto"}, "Plan.activation")


def _journal(value: Any) -> None:
    fields = {"format_version", "operation_id", "plan_digest", "phase", "prior_selection", "target_selection", "started_at", "updated_at", "failure"}
    value = obj(value, fields, "Journal")
    _version(value, "Journal")
    identifier(value["operation_id"], "Journal.operation_id")
    digest_value(value["plan_digest"], "Journal.plan_digest")
    enum(value["phase"], {"prepared", "artifact_verified", "staged", "checks_passed", "selection_committed", "postcheck_passed", "complete", "rollback_required", "rolled_back", "failed"}, "Journal.phase")
    if value["prior_selection"] is not None:
        selection(value["prior_selection"])
    selection(value["target_selection"])
    string(value["started_at"], "Journal.started_at", maximum=64)
    string(value["updated_at"], "Journal.updated_at", maximum=64)
    if value["failure"] is not None:
        string(value["failure"], "Journal.failure")


def _execution(value: Any) -> None:
    fields = {"format_version", "status", "operation_id", "plan_digest", "prior_selection", "current_selection", "executed_check_ids", "reason_code"}
    value = obj(value, fields, "ExecutionResult")
    _version(value, "ExecutionResult")
    enum(value["status"], {"staged", "active", "no_op", "rolled_back", "rolled_back_incompatible", "recovered", "stale_plan", "storage_changing", "busy", "invalid", "failed"}, "ExecutionResult.status")
    if value["operation_id"] is not None:
        identifier(value["operation_id"], "ExecutionResult.operation_id")
    if value["plan_digest"] is not None:
        digest_value(value["plan_digest"], "ExecutionResult.plan_digest")
    for name in ("prior_selection", "current_selection"):
        if value[name] is not None:
            selection(value[name])
    ids(value["executed_check_ids"], "ExecutionResult.executed_check_ids")
    if value["reason_code"] is not None:
        identifier(value["reason_code"], "ExecutionResult.reason_code")


def _policy(value: Any) -> None:
    value = obj(value, {"format_version", "known_recipe_mode", "startup_trigger", "allow_downloads"}, "ActivationPolicy")
    _version(value, "ActivationPolicy")
    enum(value["known_recipe_mode"], {"explicit", "auto_opt_in"}, "ActivationPolicy.known_recipe_mode")
    enum(value["startup_trigger"], {"none"}, "ActivationPolicy.startup_trigger")
    if boolean(value["allow_downloads"], "ActivationPolicy.allow_downloads"):
        _fail("ActivationPolicy.allow_downloads must be false")


VALIDATORS: dict[str, Callable[[Any], None]] = {
    "Column": column, "Table": table, "UsedProfile": profile,
    "AdapterIdentity": adapter, "Recipe": recipe, "Selection": selection,
    "Source": source, "SchemaSnapshot": _snapshot, "Observation": _observation,
    "Classification": _classification, "Catalogue": _catalogue, "Plan": _plan,
    "Journal": _journal, "ExecutionResult": _execution, "ActivationPolicy": _policy,
}
