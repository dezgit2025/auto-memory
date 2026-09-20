"""Companion CLI for deterministic Codex adapter diagnosis and activation."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import stat
import sys
from typing import Any, Callable

from session_recall import __version__
from session_recall.codex_metadata import StorageChangingError
from session_recall.db.connect import DatabaseBusyError

from . import factory, store
from .context import Context
from .contracts import ContractError, parse
from .engine import classify, observe, plan


MAX_PLAN_BYTES = 2 * 1024 * 1024


class ArgumentFailure(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ArgumentFailure(message)


def _parser() -> Parser:
    parser = Parser(prog="session-recall-codex-fix")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root")
    parser.add_argument("--state-db")
    parser.add_argument("--history-db")
    parser.add_argument("--sessions-root")
    parser.add_argument("--config")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check")
    check.add_argument("--auto", action="store_true")
    commands.add_parser("plan")
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("--plan", required=True)
    rollback = commands.add_parser("rollback")
    rollback.add_argument("--repair", required=True)
    commands.add_parser("assist")
    approve = commands.add_parser("approve")
    approve.add_argument("--candidate", required=True)
    approve.add_argument("--yes", action="store_true")
    candidate_apply = commands.add_parser("apply-candidate")
    candidate_apply.add_argument("--candidate", required=True)
    budget_approve = commands.add_parser("budget-approve")
    budget_approve.add_argument("--challenge", required=True)
    budget_approve.add_argument("--yes", action="store_true")
    return parser


def _emit(command: str, ok: bool, status: str, detail: Any, json_mode: bool) -> None:
    body = {
        "format_version": 1,
        "command": command,
        "ok": ok,
        "status": status,
        "detail": detail,
    }
    if json_mode:
        print(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        print(status if ok else f"error: {status}", file=sys.stdout if ok else sys.stderr)
        if command in {"assist", "approve", "apply-candidate", "budget-approve"} and detail is not None:
            print(json.dumps(detail, ensure_ascii=False, indent=2))


def _observed(context: Context) -> tuple[Context, dict[str, Any]]:
    observation = observe(context.recapture(), context)
    updated = replace(context, current_observation=observation)
    return updated, classify(observation, updated)


def _read_plan(raw: str) -> dict[str, Any]:
    path = Path(raw).expanduser()
    try:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_PLAN_BYTES:
            raise ContractError("invalid_plan")
        return parse(path.read_text(encoding="utf-8"), "Plan")
    except ContractError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ContractError("invalid_plan") from exc


def _execution_exit(result: dict[str, Any]) -> int:
    status = result["status"]
    if status in {"active", "no_op", "rolled_back", "rolled_back_incompatible", "recovered"}:
        return 0
    if status == "busy":
        return 3
    if status == "storage_changing":
        return 3
    if status == "failed":
        return 5
    return 2


def _contract_status(code: str) -> str:
    if code == "ambiguous_recipe":
        return "ambiguous_recipe"
    if code == "no_recipe":
        return "assistance_eligible"
    if code == "unmanaged_legacy":
        return "unmanaged_legacy"
    if code == "storage_changing":
        return "storage_changing"
    if code in {"stale_plan", "stale_observation", "stale_classification"}:
        return "stale_plan"
    return "invalid"


def _dispatch(args: argparse.Namespace, context: Context) -> tuple[bool, str, Any, int]:
    if args.command == "assist":
        from .assist import assist
        result = assist(context)
        status = result["status"]
        return status in {"supported", "known_repair", "action_needed"}, status, result, 0 if status in {"supported", "known_repair"} else 2
    if args.command in {"approve", "budget-approve"}:
        from . import approval
        if args.command == "approve":
            review = approval.load_review(context.managed_root, args.candidate)
            detail = {"candidate_id": args.candidate, "independent_result": review["result"]}
            if not args.yes and sys.stdin.isatty() and not args.json:
                from .assist import _diff
                print(_diff(review["request"], review["candidate"]))
        else:
            from ._assist_budget import budget_store
            ledger = budget_store(context.managed_root).read()
            detail = next((g["challenge"] for g in ledger["grants"] if g["challenge_id"] == args.challenge and g["status"] == "pending"), None)
            if detail is None:
                raise ContractError("unknown_challenge")
        confirmed = args.yes
        if not confirmed and sys.stdin.isatty() and not args.json:
            print(json.dumps(detail, indent=2))
            try:
                confirmed = input("Approve this action? Type yes: ").strip() == "yes"
            except (EOFError, KeyboardInterrupt):
                confirmed = False
        if not confirmed:
            return False, "action_needed", detail, 2
        if args.command == "approve":
            result = approval.approve(args.candidate, context, actor="local-cli-user")
        else:
            from ._assist_budget import approve_budget
            result = approve_budget(context.managed_root, args.challenge)
        return True, "approved", result, 0
    if args.command == "apply-candidate":
        from .assist import apply_candidate
        result = apply_candidate(args.candidate, context)
        return _execution_exit(result) == 0, result["status"], result, _execution_exit(result)
    if args.command == "check" and args.auto and context.policy["known_recipe_mode"] != "auto_opt_in":
        return False, "invalid", None, 2
    if args.command == "rollback":
        result = store.rollback(args.repair, context)
        return _execution_exit(result) == 0, result["status"], result, _execution_exit(result)
    if args.command == "apply":
        repair_plan = _read_plan(args.plan)
        observed, _classification = _observed(context)
        result = store.apply(repair_plan, observed)
        return _execution_exit(result) == 0, result["status"], result, _execution_exit(result)

    observed, classification = _observed(context)
    if args.command == "check" and not args.auto:
        return True, classification["status"], classification, 0
    if args.command == "check":
        if classification["status"] == "supported":
            return True, "supported", classification, 0
        if classification["status"] != "known_repair":
            return False, classification["status"], classification, 2
        repair_plan = plan(classification, observed)
        result = store.apply(repair_plan, observed)
        return _execution_exit(result) == 0, result["status"], result, _execution_exit(result)
    if classification["status"] == "supported":
        return True, "supported", classification, 0
    repair_plan = plan(classification, observed)
    return True, "planned", repair_plan, 0


def main(
    argv: list[str] | None = None,
    *,
    context_factory: Callable[[argparse.Namespace], Context] = factory.production_context,
) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in raw
    try:
        args = _parser().parse_args(raw)
    except ArgumentFailure:
        _emit("arguments", False, "invalid", None, json_mode)
        return 2
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        context = context_factory(args)
        ok, status, detail, code = _dispatch(args, context)
    except StorageChangingError:
        ok, status, detail, code = False, "storage_changing", None, 3
    except DatabaseBusyError:
        ok, status, detail, code = False, "busy", None, 3
    except FileNotFoundError:
        ok, status, detail, code = False, "invalid", None, 4
    except (sqlite3.Error, OSError):
        ok, status, detail, code = False, "invalid", None, 4
    except ContractError as exc:
        status = exc.code if args.command in {"assist", "approve", "apply-candidate", "budget-approve"} else _contract_status(exc.code)
        ok, detail, code = False, None, 3 if status == "storage_changing" else 2
    _emit(args.command, ok, status, detail, args.json)
    return code


if __name__ == "__main__":
    sys.exit(main())
