"""install-mode command — detect Claude Code surfaces and configure hooks."""
import pathlib
import sys
from ..util.format_output import output


def run(args) -> int:
    try:
        from ..backends.claude_code.install import detect_surfaces, wire_hooks
    except ImportError as e:
        print(f"error: Claude Code backend unavailable: {e}", file=sys.stderr)
        return 1

    surfaces = detect_surfaces()
    surface_data = [
        {"surface": s.name, "detected": s.detected, "path": s.path, "note": s.note}
        for s in surfaces
    ]

    detected_names = [s.name for s in surfaces if s.detected]

    setup = getattr(args, "setup", False)
    dry_run = getattr(args, "dry_run", False)

    result = {
        "surfaces": surface_data,
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
        if not getattr(args, "json", False):
            action = hook_result["action"]
            if action == "already_wired":
                print("✓ SessionStart hook already configured", file=sys.stderr)
            elif action == "dry_run":
                print(f"[dry-run] Would add SessionStart hook to {settings_path}", file=sys.stderr)
                print(f"[dry-run] Hook command: {hook_result['hook_command']}", file=sys.stderr)
            else:
                print(f"✓ SessionStart hook added to {settings_path}", file=sys.stderr)
                print(f"  Command: {hook_result['hook_command']}", file=sys.stderr)

    project = getattr(args, "project", False)
    project_path_arg = getattr(args, "project_path", None)

    if project or project_path_arg:
        import pathlib as _pl
        try:
            from ..backends.claude_code.install import write_claude_md
        except ImportError as e:
            print(f"error: Claude Code backend unavailable: {e}", file=sys.stderr)
            return 1

        claude_md = _pl.Path(project_path_arg) if project_path_arg else _pl.Path.cwd() / "CLAUDE.md"
        try:
            proj_result = write_claude_md(claude_md, dry_run=dry_run)
        except OSError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

        result["claude_md"] = proj_result
        action = proj_result["action"]
        if not getattr(args, "json", False):
            if action == "already_present":
                print(f"✓ CLAUDE.md already has session-recall block: {claude_md}")
            elif action == "dry_run":
                print(f"[dry-run] Would write session-recall block to {claude_md}")
            else:
                print(f"✓ session-recall block {action}: {claude_md}")

    if not getattr(args, "json", False):
        print(f"\nClaude Code surfaces ({len(detected_names)}/{len(surfaces)} detected):")
        for s in surfaces:
            icon = "✓" if s.detected else "✗"
            print(f"  {icon} {s.name:12} {s.note}")
        if not setup and not dry_run:
            print("\nRun with --setup to wire SessionStart hooks automatically.")

    output(result, json_mode=getattr(args, "json", False))
    return 0
