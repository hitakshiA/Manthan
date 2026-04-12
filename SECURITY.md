# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Manthan, **please report it privately** rather than opening a public issue.

**Email:** akash@manthan.dev

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Response Timeline

- **Acknowledgement:** within 48 hours
- **Initial assessment:** within 1 week
- **Fix or mitigation:** within 30 days for critical issues

## Scope

The following are in scope:
- SQL injection via the `/tools/sql` endpoint
- Sandbox escapes in the Python REPL worker
- Authentication bypass or API key exposure
- Path traversal in file upload or artifact serving
- Denial of service via crafted datasets

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | Yes       |
| < 1.0   | No        |

## Best Practices

- Never commit `.env` files or API keys
- Use `SecretStr` for all sensitive configuration
- All SQL queries go through `validate_identifier()` and parameterized execution
- The Python sandbox runs in an isolated subprocess with no network access by default
