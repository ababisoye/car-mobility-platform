# Security policy

## Supported scope

The `main` branch represents the current demonstration. It is not approved for real customer identity documents, payment-card data or production rental operations.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials or customer information. Use GitHub's **Security → Report a vulnerability** flow when it is available. If private reporting is unavailable, contact the repository owner through the GitHub profile without including sensitive evidence in the first message.

Include the affected route or component, impact, safe reproduction steps and a suggested mitigation when possible. Never test against infrastructure or data you do not own or have permission to assess.

## Credential exposure

If a credential may have been committed or disclosed, revoke or rotate it immediately. Removing it from the latest commit is not sufficient because Git history and clones may retain it.
