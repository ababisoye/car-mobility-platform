# Controlled release and rollback runbook

This runbook prepares deployment automation without deploying anything by itself. The public demo URL targets the Lambda `live` alias, so uploading code does not change customer traffic until the alias is promoted.

## Safety model

1. A human manually starts the `Controlled demo release` workflow.
2. GitHub checks out the selected branch, tag or full commit SHA.
3. Tests, packaging, Terraform formatting and validation must pass before AWS credentials are requested.
4. The `demo-release` GitHub environment provides an approval boundary.
5. GitHub exchanges its OIDC token for short-lived AWS credentials; no AWS access key is stored.
6. A deployment publishes an immutable Lambda version, waits for the update, and then moves `live` to that version.
7. A rollback verifies an existing version and moves only the alias.

Terraform creates the initial alias but deliberately ignores later `function_version` drift because the release workflow owns that pointer. This prevents a routine infrastructure plan from silently undoing a promotion or rollback.

The release role cannot create infrastructure, edit IAM, read DynamoDB data or delete the function. Its inline policy is limited to inspecting the demo Lambda, uploading code, publishing versions and moving its alias.

## One-time setup

Do not perform these steps until you intentionally approve an AWS deployment and its possible cost.

1. Deploy the demo infrastructure once with Terraform. This creates the initial published Lambda version and `live` alias.
2. Create the GitHub OIDC role from `infra/github-release-role` using temporary administrator credentials:

   ```powershell
   Copy-Item infra/github-release-role/terraform.tfvars.example infra/github-release-role/terraform.tfvars
   Set-Location infra/github-release-role
   terraform init
   terraform plan -out release-role.tfplan
   terraform apply release-role.tfplan
   terraform output -raw release_role_arn
   ```

   If the AWS account already has the GitHub OIDC provider, import that provider into this Terraform state instead of attempting to create a duplicate.

3. In GitHub, create an environment named `demo-release`. Limit deployment branches to `main` and add a required reviewer where the repository plan supports it.
4. Add the output ARN as the environment secret `AWS_RELEASE_ROLE_ARN`.
5. Add environment variables `AWS_ACCOUNT_ID` and `AWS_REGION` (`af-south-1` by default).

## Deploy a verified revision

Open **Actions → Controlled demo release → Run workflow**:

- Choose `deploy`.
- Enter `main`, a release tag or preferably the full commit SHA reviewed for release.
- Leave `rollback_version` empty.
- Review the environment approval request before allowing AWS access.

The workflow summary records the source ref and published Lambda version. Keep that version number with the release notes.

## Roll back

Open the same manual workflow:

- Choose `rollback`.
- Enter the current trusted source ref so the verification job remains reproducible.
- Enter the previous numeric Lambda version from a successful release summary.
- Approve the protected environment job.

Rollback changes the `live` alias and does not rebuild or overwrite the older version. It does not reverse DynamoDB records or schema changes, so application changes must remain backward compatible with stored data.

## Emergency checks

After either operation:

1. Request `/health` from the demo URL.
2. Submit a non-sensitive test booking.
3. Confirm the operations dashboard can read the booking.
4. Confirm CloudWatch has no new Lambda errors.
5. Roll back the alias if the smoke test fails.

Never paste AWS credentials, webhook secrets, admin passwords or customer data into workflow inputs or logs.
