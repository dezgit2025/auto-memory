"""serve command — start MCP tool server."""
import sys

_IMPORT_ERROR_MSG = (
    "MCP support requires the 'mcp' package.\n"
    "Install with: pip install \"auto-memory[mcp]\""
)


def run(args) -> int:
    backend_name = getattr(args, "backend", None)
    try:
        from ..mcp_server import run_stdio
        run_stdio(backend_name)
        return 0
    except ImportError:
        print(_IMPORT_ERROR_MSG, file=sys.stderr)
        return 1
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
