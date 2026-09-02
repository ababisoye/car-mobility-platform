# Contributing

Thank you for helping improve the chauffeur-driven mobility platform.

## Before opening a change

- Use an issue for a bug, proposal or material architecture change.
- Never include customer data, credentials, AWS account details, Terraform state or generated deployment packages.
- Keep the zero-funding demo within the controls documented in `docs/zero-funding-policy.md` unless the proposal explicitly targets a later funded stage.
- Do not deploy infrastructure as part of a contribution.

## Local verification

From the repository root, run:

```powershell
python -m unittest discover -s tests -v
terraform fmt -check -recursive infra
```

If Terraform is available and the relevant directory has been initialized, also run `terraform validate`. A pull request must leave GitHub Actions green.

## Pull requests

Keep each pull request focused on one outcome. Explain the business reason, security and cost effects, tests performed and whether the change alters the API or data model. Update the OpenAPI contract and documentation when behavior changes.

By submitting a contribution, you confirm that you have the right to submit it. The repository currently has no open-source license; public visibility does not grant permission to reuse the code.
