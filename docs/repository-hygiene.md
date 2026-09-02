# Public repository hygiene

CI enumerates Git-tracked files and rejects common AWS access keys, GitHub tokens, private-key blocks, Slack tokens and live Stripe keys. It also rejects tracked Terraform state, real `.tfvars`, `.env` files, private-key containers, deployment plans and ZIP packages.

This is a high-confidence preventive check, not a complete secret-scanning service. Before publishing or responding to a suspected leak, review Git history and rotate the affected credential immediately; deleting it from the latest commit is not sufficient.

Local credential and Terraform working files remain covered by `.gitignore`. The guardrail performs no deployment and uses no paid service.
