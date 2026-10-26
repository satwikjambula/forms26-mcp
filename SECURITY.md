# Security

This alpha tool reads project files and can optionally inspect database metadata. It has not undergone a security audit or live Oracle certification.

Do not post credentials, connection wallets, real customer Forms exports, application data or working exploits in public issues.

To report a vulnerability, use this repository's **Security → Report a vulnerability** option when available. If private reporting is unavailable, open an issue asking the maintainer for a private reporting channel without including sensitive details.

Reports should describe affected versions, the relevant tool or file operation, expected impact and a synthetic reproduction. No response-time commitment is currently offered.

Run against a dedicated export directory and an account with only the database visibility required. Legacy file content is untrusted input. The host assistant's model provider may receive source returned by MCP tools; configure it according to your project's data-handling requirements.
