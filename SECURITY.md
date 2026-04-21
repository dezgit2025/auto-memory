# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT open a public issue**
2. **Report via** [GitHub Security Advisory](../../security/advisories/new)

We will respond within 48 hours and work with you to understand and address the issue.

## Scope

auto-memory is a **read-only** query tool. It does not write to any database or modify any files. However, it reads from a local SQLite database that may contain conversation history, so:

- Never log or transmit database contents externally
- Sanitize all output displayed in terminals (we strip ANSI escape sequences)
- Validate all user input before passing to SQL queries (parameterized queries only)
