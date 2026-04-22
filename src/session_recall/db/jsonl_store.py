"""JSONL-based session store for Copilot CLI 1.0.34+.

Parses events.jsonl from ~/.copilot/session-state/{sessionId}/events.jsonl
and provides a query interface mimicking the SQLite schema.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


class JSONLStore:
    """In-memory session store loaded from JSONL event files."""

    def __init__(self):
        """Initialize empty store."""
        self.sessions: dict[str, dict[str, Any]] = {}
        self.turns: list[dict[str, Any]] = []
        self.session_files: list[dict[str, Any]] = []
        self.checkpoints: list[dict[str, Any]] = []
        self.load_from_disk()

    def load_from_disk(self) -> None:
        """Load all sessions from ~/.copilot/session-state/*/events.jsonl."""
        session_dir = Path.home() / ".copilot" / "session-state"
        if not session_dir.exists():
            return

        for session_path in session_dir.iterdir():
            if not session_path.is_dir():
                continue
            events_file = session_path / "events.jsonl"
            if not events_file.exists():
                continue
            self._load_session(events_file)

    def _load_session(self, events_file: Path) -> None:
        """Load a single session from events.jsonl."""
        session_id: Optional[str] = None
        repository = "unknown"
        branch = "unknown"
        summary = ""
        created_at = ""
        updated_at = ""
        cwd = ""
        turn_count = 0
        user_messages: list[str] = []
        assistant_responses: list[str] = []
        file_accesses: dict[str, dict[str, Any]] = {}

        try:
            with open(events_file) as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")
                    event_data = event.get("data", {})
                    timestamp = event.get("timestamp", "")

                    # Extract session metadata from session.start
                    if event_type == "session.start":
                        session_id = event_data.get("sessionId")
                        created_at = timestamp
                        updated_at = timestamp
                        ctx = event_data.get("context", {})
                        cwd = ctx.get("cwd", "unknown")
                        # Try to extract repo from cwd
                        repository = self._infer_repo(cwd)

                    # Track turns
                    elif event_type == "assistant.turn_end":
                        turn_count += 1
                        updated_at = timestamp

                    # Track user messages
                    elif event_type == "user.message":
                        content = event_data.get("content", "")
                        if content:
                            user_messages.append(content)

                    # Track assistant responses
                    elif event_type == "assistant.message":
                        content = event_data.get("content", "")
                        if content:
                            assistant_responses.append(content)

                    # Track tool executions for file access
                    elif event_type == "tool.execution_complete":
                        tool_result = event_data.get("result", {})
                        if isinstance(tool_result, str):
                            tool_result = {}
                        # Extract files from tool output if present
                        self._extract_files_from_tool(
                            session_id, tool_result,
                            event_data.get("toolName", "unknown"),
                            turn_count, timestamp, file_accesses
                        )

            # Create session record if we have a valid session
            if session_id:
                # Generate summary from user messages
                summary = " ".join(user_messages[:2]) if user_messages else "No messages"
                if len(summary) > 200:
                    summary = summary[:197] + "..."

                self.sessions[session_id] = {
                    "id": session_id,
                    "repository": repository,
                    "branch": branch,
                    "summary": summary,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "turns_count": turn_count,
                    "files_count": len(file_accesses),
                    "cwd": cwd,
                }

                # Add file records
                for file_path, file_info in file_accesses.items():
                    self.session_files.append({
                        "session_id": session_id,
                        "file_path": file_path,
                        "tool_name": file_info["tool"],
                        "turn_index": file_info["turn"],
                        "first_seen_at": file_info["timestamp"],
                    })

                # Add turn records
                for i in range(turn_count):
                    user_msg = user_messages[i] if i < len(user_messages) else ""
                    assist_msg = assistant_responses[i] if i < len(assistant_responses) else ""
                    self.turns.append({
                        "session_id": session_id,
                        "turn_index": i,
                        "user_message": user_msg,
                        "assistant_response": assist_msg,
                        "timestamp": updated_at,
                    })

        except Exception:
            # Silently skip malformed session files
            pass

    def _infer_repo(self, cwd: str) -> str:
        """Infer repository name from working directory path."""
        if not cwd or cwd == "unknown":
            return "unknown"
        # Return the last path component (repo name)
        return Path(cwd).name or "unknown"

    def _extract_files_from_tool(
        self,
        session_id: Optional[str],
        tool_result: dict[str, Any],
        tool_name: str,
        turn_index: int,
        timestamp: str,
        file_accesses: dict[str, dict[str, Any]],
    ) -> None:
        """Extract file paths from tool execution result."""
        if not session_id:
            return

        # Get output text from various possible locations
        output_text = ""
        if isinstance(tool_result, dict):
            # Try common result field names
            output_text = (
                tool_result.get("content", "") or
                tool_result.get("output", "") or
                tool_result.get("detailedContent", "") or
                str(tool_result)
            )
        else:
            output_text = str(tool_result)

        # Extract all file paths mentioned in output
        # Look for paths with common file extensions
        import re
        # Match paths like /Users/..., src/..., ./..., etc.
        path_pattern = r'[./\w\-]+(?:/[\w.\-]+)+\.\w{1,4}(?=[\s\n,\)\]\}]|$)'
        matches = re.findall(path_pattern, output_text)

        for file_path in matches:
            # Skip common false positives
            if any(skip in file_path for skip in ['http://', 'https://', '..', 'venv', 'node_modules']):
                continue
            if file_path not in file_accesses:
                file_accesses[file_path] = {
                    "tool": tool_name,
                    "turn": turn_index,
                    "timestamp": timestamp,
                }

    def query(self, sql: str, params: tuple = ()) -> "QueryResult":
        """Execute a SQL-like query on the in-memory data.

        Supports subset of SQL needed for auto-memory:
        - SELECT with WHERE, ORDER BY, LIMIT, JOIN
        """
        return QueryExecutor(self).execute(sql, params)


class QueryResult:
    """Result set from a query."""

    def __init__(self, rows: list[dict[str, Any]]):
        """Initialize with list of row dicts."""
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        """Return all rows."""
        return self.rows

    def fetchone(self) -> Optional[dict[str, Any]]:
        """Return first row or None."""
        return self.rows[0] if self.rows else None


class QueryExecutor:
    """Simple SQL query executor for in-memory data."""

    def __init__(self, store: JSONLStore):
        """Initialize with store."""
        self.store = store

    def execute(self, sql: str, params: tuple = ()) -> QueryResult:
        """Execute a query."""
        sql_lower = sql.lower().strip()

        # Parse and normalize SQL
        if sql_lower.startswith("select"):
            return self._execute_select(sql, params)
        else:
            return QueryResult([])

    def _execute_select(self, sql: str, params: tuple) -> QueryResult:
        """Execute SELECT query."""
        # This is a simplified parser—handles the specific queries used by auto-memory
        sql_lower = sql.lower().strip()

        # Preprocess: remove subqueries and evaluate them
        # This handles queries like "SELECT ... (SELECT COUNT(*) ...) as turns_count ..."
        import re
        sql_processed = sql
        
        # Find all subqueries and replace with placeholder values
        subquery_pattern = r'\(SELECT COUNT\(\*\) FROM (\w+) (?:t|f) WHERE (?:t|f)\.(\w+) = s\.id\)'
        subqueries = re.findall(subquery_pattern, sql_processed, re.IGNORECASE)
        
        for table, col in subqueries:
            # For now, just remove the subqueries - we'll compute counts separately
            sql_processed = re.sub(subquery_pattern, '0', sql_processed, count=1, flags=re.IGNORECASE)

        sql_lower = sql_processed.lower()

        # Handle COUNT(*) queries
        if "count(*)" in sql_lower:
            if "from sessions" in sql_lower:
                count = len(self.store.sessions)
            elif "from session_files" in sql_lower:
                count = len(self.store.session_files)
            elif "from checkpoints" in sql_lower:
                count = len(self.store.checkpoints)
            elif "from turns" in sql_lower:
                count = len(self.store.turns)
            else:
                count = 0
            return QueryResult([{"COUNT(*)": count}])

        # Handle search_index MATCH queries (FTS fallback) 
        if "search_index" in sql_lower and "match" in sql_lower:
            return self._search_fts_fallback(sql, params)

        # Parse table name from processed SQL
        if "from sessions" in sql_lower:
            return self._select_from_sessions(sql_processed, params)
        elif "from session_files" in sql_lower:
            return self._select_from_files(sql_processed, params)
        elif "from checkpoints" in sql_lower:
            return self._select_from_checkpoints(sql_processed, params)
        elif "from turns" in sql_lower:
            return self._select_from_turns(sql_processed, params)

        return QueryResult([])

    def _search_fts_fallback(self, sql: str, params: tuple) -> QueryResult:
        """Fallback for FTS search — use simple substring matching."""
        # Extract search query from params (usually first param)
        if not params:
            return QueryResult([])

        search_term = params[0]
        # Remove FTS5 syntax characters for simple substring search
        import re
        search_term = re.sub(r'[*:"()]', '', search_term)

        results = []
        for session in self.store.sessions.values():
            # Search in summary
            if search_term.lower() in session.get("summary", "").lower():
                results.append({
                    "content": session.get("summary", ""),
                    "session_id": session.get("id", ""),
                    "source_type": "summary",
                    "summary": session.get("summary", ""),
                    "created_at": session.get("created_at", ""),
                    "repository": session.get("repository", ""),
                })

        # Also search in file paths
        for file_rec in self.store.session_files:
            if search_term.lower() in file_rec.get("file_path", "").lower():
                session_id = file_rec.get("session_id", "")
                if session_id in self.store.sessions:
                    sess = self.store.sessions[session_id]
                    results.append({
                        "file_path": file_rec.get("file_path", ""),
                        "session_id": session_id,
                        "tool_name": file_rec.get("tool_name", ""),
                        "first_seen_at": file_rec.get("first_seen_at", ""),
                        "summary": sess.get("summary", ""),
                        "created_at": sess.get("created_at", ""),
                        "repository": sess.get("repository", ""),
                    })

        # Apply limit if present
        if "limit" in sql.lower():
            # Find limit parameter
            limit_sql = sql.lower()
            limit_idx = limit_sql.find("limit")
            sql_before_limit = sql[:limit_idx]
            question_marks_before = sql_before_limit.count("?")
            if question_marks_before < len(params):
                limit = params[question_marks_before]
                results = results[:limit]

        return QueryResult(results)

    def _select_from_sessions(self, sql: str, params: tuple) -> QueryResult:
        """Execute SELECT from sessions."""
        from datetime import timezone
        
        rows = list(self.store.sessions.values())

        # Apply WHERE filters based on parsed SQL
        # Handle: created_at >= datetime('now', ?)
        if "created_at >=" in sql.lower() and "datetime" in sql.lower():
            if params and len(params) > 0:
                try:
                    days_str = params[0]
                    cutoff_days = int(days_str.lstrip("-").split()[0])
                    # Use timezone-aware UTC datetime
                    cutoff = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=cutoff_days)
                    rows = [r for r in rows if self._parse_datetime(r.get("created_at", "")) and 
                            self._parse_datetime(r.get("created_at", "")) >= cutoff]
                except (ValueError, IndexError):
                    pass

        # Handle repository filter: WHERE s.repository = ?
        if "WHERE s.repository = ?" in sql or "where s.repository = ?" in sql.lower():
            # The first parameter would be the repo name, unless there's a datetime one first
            if "datetime" in sql.lower():
                # Datetime is first param, repo is second
                if len(params) > 1:
                    repo = params[1]
                    rows = [r for r in rows if r.get("repository") == repo]
            elif params:
                repo = params[0]
                if repo and repo != "all":
                    rows = [r for r in rows if r.get("repository") == repo]

        # Apply ORDER BY DESC (created_at DESC is common)
        if "ORDER BY" in sql or "order by" in sql:
            rows.sort(
                key=lambda r: self._parse_datetime(r.get("created_at", "")) or datetime.min,
                reverse=True
            )

        # Apply LIMIT
        # Count ? in SQL before LIMIT to find the limit parameter
        if "LIMIT" in sql or "limit" in sql:
            limit_sql = sql.lower()
            limit_idx = limit_sql.find("limit")
            sql_before_limit = sql[:limit_idx]
            question_marks_before_limit = sql_before_limit.count("?")
            
            if question_marks_before_limit < len(params):
                limit = params[question_marks_before_limit]
                rows = rows[:limit]
            elif "LIMIT ?" in sql or "limit ?" in sql.lower():
                # Fallback: try to find limit as last parameter
                if params:
                    limit = params[-1]
                    rows = rows[:limit]

        return QueryResult(rows)

    def _select_from_files(self, sql: str, params: tuple) -> QueryResult:
        """Execute SELECT from session_files."""
        rows = list(self.store.session_files)

        # Apply WHERE filters
        if "where" in sql.lower():
            rows = self._apply_where(rows, sql, params)

        # Apply ORDER BY
        if "order by" in sql.lower():
            rows = self._apply_order_by(rows, sql)

        # Apply LIMIT
        if "limit" in sql.lower():
            rows = self._apply_limit(rows, sql, params)

        return QueryResult(rows)

    def _select_from_checkpoints(self, sql: str, params: tuple) -> QueryResult:
        """Execute SELECT from checkpoints."""
        rows = list(self.store.checkpoints)

        if "where" in sql.lower():
            rows = self._apply_where(rows, sql, params)

        if "order by" in sql.lower():
            rows = self._apply_order_by(rows, sql)

        if "limit" in sql.lower():
            rows = self._apply_limit(rows, sql, params)

        return QueryResult(rows)

    def _select_from_turns(self, sql: str, params: tuple) -> QueryResult:
        """Execute SELECT from turns."""
        rows = list(self.store.turns)

        if "where" in sql.lower():
            rows = self._apply_where(rows, sql, params)

        if "order by" in sql.lower():
            rows = self._apply_order_by(rows, sql)

        if "limit" in sql.lower():
            rows = self._apply_limit(rows, sql, params)

        return QueryResult(rows)

    def _apply_where(self, rows: list, sql: str, params: tuple) -> list:
        """Apply WHERE clause filters."""
        # Extract WHERE clause
        where_idx = sql.lower().find("where")
        if where_idx == -1:
            return rows

        where_clause = sql[where_idx + 5:]
        # Find end of WHERE (before ORDER BY, LIMIT, etc)
        for keyword in ["order by", "limit", ";"]:
            idx = where_clause.lower().find(keyword)
            if idx != -1:
                where_clause = where_clause[:idx]

        where_clause = where_clause.strip()

        # Filter rows based on WHERE conditions
        filtered = []

        # Track parameter index for parameterized queries
        for row in rows:
            match = True

            # Check datetime >= condition (e.g., created_at >= datetime('now', ?) )
            if ">=" in where_clause and "datetime" in where_clause:
                col = self._extract_column(where_clause)
                # Extract the days parameter from query
                # The params tuple contains strings like "-30 days"
                if col and params and len(params) > 0:
                    try:
                        days_str = params[0]  # e.g., "-30 days"
                        cutoff_days = int(days_str.lstrip("-").split()[0])
                        cutoff = datetime.utcnow() - timedelta(days=cutoff_days)
                        row_date = self._parse_datetime(row.get(col, ""))
                        if row_date and row_date >= cutoff:
                            match = True
                        else:
                            match = False
                    except (ValueError, IndexError):
                        # If we can't parse, include the row
                        match = True

            # Check simple = condition
            elif "=" in where_clause and "?" in where_clause and "datetime" not in where_clause:
                parts = where_clause.split("=")
                if len(parts) == 2:
                    col = parts[0].strip().split()[-1]  # Get last part (table.col -> col)
                    # Find which parameter this corresponds to
                    question_count = sql[:sql.lower().find("where")].count("?")
                    if question_count < len(params):
                        param_val = params[question_count]
                        if row.get(col) != param_val:
                            match = False

            if match:
                filtered.append(row)

        return filtered

    def _extract_column(self, where_clause: str) -> Optional[str]:
        """Extract column name from WHERE clause."""
        parts = where_clause.split()
        if len(parts) > 0:
            col = parts[0].split(".")[-1]  # Handle table.col
            return col
        return None

    def _parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """Parse ISO datetime string to UTC aware datetime."""
        if not dt_str:
            return None
        try:
            # Try ISO format with Z (UTC indicator)
            if dt_str.endswith("Z"):
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                return dt
            # Try ISO format with timezone offset
            elif "+" in dt_str or dt_str.count("-") > 2:
                return datetime.fromisoformat(dt_str)
            # No timezone - assume UTC and add timezone info
            else:
                dt = datetime.fromisoformat(dt_str)
                # Make it timezone-aware (UTC)
                from datetime import timezone
                return dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    def _apply_order_by(self, rows: list, sql: str) -> list:
        """Apply ORDER BY sorting."""
        order_idx = sql.lower().find("order by")
        if order_idx == -1:
            return rows

        order_clause = sql[order_idx + 8:].strip()
        # Find end of ORDER BY
        limit_idx = order_clause.lower().find("limit")
        if limit_idx != -1:
            order_clause = order_clause[:limit_idx].strip()

        # Parse "col [ASC|DESC]"
        parts = order_clause.split()
        col = parts[0].split(".")[-1]  # Handle table.col
        reverse = len(parts) > 1 and parts[1].upper() == "DESC"

        try:
            rows.sort(
                key=lambda r: self._parse_datetime(r.get(col, "")) or r.get(col, ""),
                reverse=reverse
            )
        except Exception:
            pass

        return rows

    def _apply_limit(self, rows: list, sql: str, params: tuple) -> list:
        """Apply LIMIT clause."""
        limit_idx = sql.lower().find("limit")
        if limit_idx == -1:
            return rows

        limit_clause = sql[limit_idx + 5:].strip()
        # Check if LIMIT is ? (parameter) or a number
        if "?" in limit_clause:
            # Find which parameter index this is
            question_marks_before = sql[:limit_idx].count("?")
            if question_marks_before < len(params):
                limit = params[question_marks_before]
                return rows[:limit]
        else:
            try:
                limit = int(limit_clause.split()[0])
                return rows[:limit]
            except Exception:
                pass

        return rows
