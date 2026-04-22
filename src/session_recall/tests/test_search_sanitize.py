"""Tests for FTS5 query sanitization in search command."""
from session_recall.commands.search import sanitize_fts5_query


class TestSanitizeFTS5Query:
    """Cover all crash cases from the adversarial gap analysis."""

    def test_dot_in_filename(self):
        assert sanitize_fts5_query("CLAUDE.md") == '"CLAUDE.md"'

    def test_dot_in_python_file(self):
        assert sanitize_fts5_query("test.py") == '"test.py"'

    def test_hyphen_treated_as_not(self):
        assert sanitize_fts5_query("session-recall") == '"session-recall"'

    def test_parentheses_grouping(self):
        assert sanitize_fts5_query("function()") == '"function()"'

    def test_empty_string_returns_none(self):
        assert sanitize_fts5_query("") is None

    def test_whitespace_only_returns_none(self):
        assert sanitize_fts5_query("   ") is None

    def test_normal_word_gets_prefix_wildcard(self):
        assert sanitize_fts5_query("OAuth") == "OAuth*"

    def test_multi_word_all_get_prefix(self):
        assert sanitize_fts5_query("memory system") == "memory* system*"

    def test_mixed_special_and_normal(self):
        result = sanitize_fts5_query("fix CLAUDE.md now")
        assert result == 'fix* "CLAUDE.md" now*'

    def test_double_quotes_escaped(self):
        result = sanitize_fts5_query('say "hello"')
        assert '""hello""' in result

    def test_asterisk_special(self):
        result = sanitize_fts5_query("*.py")
        assert result.startswith('"')

    def test_colon_special(self):
        result = sanitize_fts5_query("key:value")
        assert result == '"key:value"'

    def test_slash_in_path(self):
        result = sanitize_fts5_query("src/main.py")
        assert result == '"src/main.py"'
