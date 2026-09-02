# Demo access-control model

The zero-funding dashboard supports two staff roles while keeping the deployment dependency-free. Both credentials are stored only as salted PBKDF2 hashes. The dashboard submits the entered credential in `x-staff-password` over HTTPS and receives the resolved role from `GET /admin/session`.

| Capability | Administrator | Operator |
|---|---:|---:|
| View bookings, vehicles, chauffeurs and notifications | Yes | Yes |
| Update booking workflow | Yes | Yes |
| Issue quotes and payment requests | Yes | Yes |
| Assign available vehicles and chauffeurs | Yes | Yes |
| Process notification-outbox records | Yes | Yes |
| Create vehicles or chauffeurs | Yes | No |
| Change fleet or chauffeur availability | Yes | No |

Public customers can submit booking requests and read the limited status, quote and payment endpoints when they possess the booking reference. Payment-provider events use a separate signed webhook identity and never receive staff access.

## Local demonstration

- Administrator password: `demo-admin`
- Operator password: `demo-operator`

The dashboard hides fleet-creation forms and locks availability controls for operators. The API independently enforces the same rules; hiding a control is not treated as authorization.

## Deployment configuration

Run `scripts/generate-admin-password-hash.py` separately for the administrator and operator passwords. Store the results in the ignored `terraform.tfvars` file as `admin_password_hash` and `operator_password_hash`. Use distinct passwords and never commit their hashes or plaintext values.

`operator_password_hash` is optional. Leaving it empty disables operator login without weakening administrator authentication.

The helper, local preview, Terraform validation and Lambda runtime enforce the same PBKDF2 work-factor floor of 210,000 iterations. Runtime validation also requires at least 16 salt bytes, an exact 32-byte SHA-256 digest and caps iterations at 2,000,000 to prevent an unsafe configuration from weakening authentication or exhausting request time.

## Production boundary

This model demonstrates authorization but is not production identity. Shared role passwords cannot provide individual attribution, MFA, immediate per-user revocation, account recovery or durable audit history. Before handling real bookings, replace the password verifier with Cognito or another managed identity provider and require:

- individual staff accounts and MFA;
- managed groups mapped to application roles;
- short-lived tokens validated by a trusted authorizer;
- login throttling, lockout and recovery controls;
- durable, access-controlled audit records tied to a user ID;
- joiner, mover and leaver procedures.

Structured logs include `actor_role` for operational diagnosis, but their one-day retention is intentionally not a compliance audit system.
