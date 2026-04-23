from session_recall.commands.export import _to_markdown


def test_to_markdown_basic():
    sessions = [{"id": "abc123", "repository": "foo/bar", "branch": "main",
                 "created_at": "2026-01-15", "summary": "fix bug",
                 "turns": [{"user": "hello", "assistant": "world"}],
                 "files": [{"file_path": "/repo/main.py", "tool_name": "Edit"}]}]
    md = _to_markdown(sessions)
    assert "abc123" in md
    assert "foo/bar" in md
    assert "hello" in md
    assert "main.py" in md


def test_to_markdown_empty():
    assert _to_markdown([]) == ""
