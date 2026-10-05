# Security policy

## Reporting

Please report security issues privately to the repository maintainers. Do not
open a public issue containing credentials, access tokens, personal data, or a
working exploit.

## Operational guidance

- Keep `.env` outside version control and rotate any credential that appears in logs or commits.
- Give platform tokens only the minimum scopes needed for publishing.
- Start with `DRY_RUN=true` and `AUTO_PUBLISH=false`.
- Use outbound network controls in production so the service can reach only configured sources,
  model providers, and publication APIs.
- Scraped content is untrusted. The application converts HTML to plain text, flags common prompt
  injection patterns, and supplies source text to the LLM only inside a delimited data object.
- The quality gate is a safety layer, not a guarantee. Human approval remains recommended for
  high-impact accounts.
