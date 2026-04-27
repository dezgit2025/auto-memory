"""install-mode command — detect Claude Code surfaces and configure hooks."""
import pathlib
import sys
from ..util.format_output import output


def _print_hook_status(hook_result: dict, settings_path: pathlib.Path) -> None:
    action = hook_result["action"]
    if action == "already_wired":
        print("✓ SessionStart hook already configured", file=sys.stderr)
    elif action == "dry_run":
        print(f"[dry-run] Would add SessionStart hook to {settings_path}", file=sys.stderr)
        print(f"[dry-run] Hook command: {hook_result['hook_command']}", file=sys.stderr)
    else:
        print(f"✓ SessionStart hook added to {settings_path}", file=sys.stderr)
        print(f"  Command: {hook_result['hook_command']}", file=sys.stderr)


def _print_claude_md_status(proj_result: dict, claude_md: pathlib.Path) -> None:
    action = proj_result["action"]
    if action == "already_present":
        print(f"✓ CLAUDE.md already has session-recall block: {claude_md}")
    elif action == "dry_run":
        print(f"[dry-run] Would write session-recall block to {claude_md}")
    else:
        print(f"✓ session-recall block {action}: {claude_md}")


def _print_mcp_status(mcp_result: dict, config_path: pathlib.Path) -> None:
    action = mcp_result["action"]
    if action == "already_wired":
        print(f"✓ MCP server already configured: {config_path}", file=sys.stderr)
    elif action == "dry_run":
        print(f"[dry-run] Would add session-recall MCP server to {config_path}", file=sys.stderr)
    else:
        print(f"✓ MCP server wired: {config_path}", file=sys.stderr)


def run(args) -> int:
    try:
        from ..backends.claude_code.install import (
            _default_mcp_config_path,
            detect_surfaces,
            wire_hooks,
            wire_mcp_config,
            write_claude_md,
        )
    except ImportError as e:
        print(f"error: Claude Code backend unavailable: {e}", file=sys.stderr)
        return 1

    setup = getattr(args, "setup", False)
    dry_run = getattr(args, "dry_run", False)
    mcp_flag = getattr(args, "mcp", False)
    project = getattr(args, "project", False)
    project_path_arg = getattr(args, "project_path", None)
    json_mode = getattr(args, "json", False)

    surfaces = detect_surfaces()
    detected_names = [s.name for s in surfaces if s.detected]

    result: dict = {
        "surfaces": [
            {"surface": s.name, "detected": s.detected, "path": s.path, "note": s.note}
            for s in surfaces
        ],
        "detected": detected_names,
    }

    if setup or dry_run:
        settings_path = pathlib.Path.home() / ".claude" / "settings.json"
        try:
            hook_result = wire_hooks(settings_path, dry_run=dry_run)
        except (ValueError, OSError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        result["hook_setup"] = hook_result
        if not json_mode:
            _print_hook_status(hook_result, settings_path)

    if project or project_path_arg:
        claude_md = pathlib.Path(project_path_arg) if project_path_arg else pathlib.Path.cwd() / "CLAUDE.md"
        try:
            proj_result = write_claude_md(claude_md, dry_run=dry_run)
        except (OSError, ValueError, UnicodeDecodeError) as e:
            print(f"error writing {claude_md}: {e}", file=sys.stderr)
            return 1
        result["claude_md"] = proj_result
        if not json_mode:
            _print_claude_md_status(proj_result, claude_md)

    if mcp_flag:
        config_path = _default_mcp_config_path()
        try:
            mcp_result = wire_mcp_config(config_path, dry_run=dry_run)
        except (ValueError, OSError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        result["mcp_config"] = mcp_result
        if not json_mode:
            _print_mcp_status(mcp_result, config_path)

    if not json_mode:
        print(f"\nClaude Code surfaces ({len(detected_names)}/{len(surfaces)} detected):")
        for s in surfaces:
            icon = "✓" if s.detected else "✗"
            print(f"  {icon} {s.name:12} {s.note}")
        no_actions = not (setup or dry_run or project or project_path_arg or mcp_flag)
        if no_actions:
            print("\nRun with --setup to wire SessionStart hooks automatically.")

    output(result, json_mode=json_mode)
    return 0
