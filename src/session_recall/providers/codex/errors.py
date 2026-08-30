"""Codex provider exceptions with CLI exit-code mapping (plan §4.4).

Exit codes:
  0 success (incl. valid empty result)
  1 session not found
  2 usage / schema drift / ambiguity / config / JSON1 failure
  3 SQLite busy after bounded retries
  4 required Codex database not found (storage_missing / storage_version_changed)
"""


class CodexError(Exception):
    """Base for all Codex provider errors."""

    exit_code = 2

    def __init__(self, message: str = ""):
        super().__init__(message)
        self.message = message


class CodexStorageMissing(CodexError):
    """A required Codex database file is absent.

    ``code`` distinguishes the two diagnoses (§16 Fix 6):
      - ``storage_missing``          — no Codex storage at all
      - ``storage_version_changed``  — sibling versioned file(s) found
    """

    exit_code = 4

    def __init__(self, message: str, code: str = "storage_missing", found=None):
        super().__init__(message)
        self.code = code
        self.found = list(found or [])


class CodexBusy(CodexError):
    """SQLite stayed locked after bounded retries."""

    exit_code = 3


class CodexSchemaDrift(CodexError):
    """Fixed schema pre-flight failed; no query was executed."""

    exit_code = 2

    def __init__(self, message: str, differences=None):
        super().__init__(message)
        self.differences = list(differences or [])


class CodexNotFound(CodexError):
    """Requested session id matched nothing."""

    exit_code = 1


class CodexAmbiguousId(CodexError):
    """Session id prefix matched more than one thread."""

    exit_code = 2

    def __init__(self, prefix: str, candidates):
        self.prefix = prefix
        self.candidates = list(candidates)
        super().__init__(
            f"session id '{prefix}' matches {len(self.candidates)} sessions"
            " — add more characters"
        )


class CodexUsageError(CodexError):
    """Bad arguments or configuration."""

    exit_code = 2
