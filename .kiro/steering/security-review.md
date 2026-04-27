---
inclusion: always
---

# Security Review Checklist

Before completing any code change, verify:

- No secrets, API keys, or credentials in source code
- User inputs are validated before use
- SQL queries use parameterized statements
- Authentication checks are present on protected routes
- Error messages don't leak internal implementation details
- Dependencies are from trusted sources with no known critical vulnerabilities
