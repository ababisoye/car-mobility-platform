# Luxury Vehicle Rental - AWS Infrastructure

This repository contains the AWS Terraform foundation for the chauffeur-driven luxury vehicle rental MVP.

## Zero-funding mode

The recommended starting point is `infra/environments/demo`. It replaces all always-running infrastructure with:

- One Python Lambda function with 128 MB memory and concurrency capped at one
- One Lambda Function URL, with no load balancer or API Gateway
- One DynamoDB table using 1 provisioned read and 1 provisioned write unit
- One-day CloudWatch log retention
- Automatic deletion of booking requests after 30 days
- A USD 1 actual and forecast budget notification

The function serves the mobile booking form and its small API from one deployment. It is a demonstration, not a production rental platform. It deliberately does not collect payments or identity documents.

AWS Budgets only sends alerts; it is not a hard spending cap. A new AWS Free account plan prevents charges while the plan is active, but it ends after six months or when credits are exhausted. Keep a local export of anything important.

## Current scope

- Separate non-production and production roots
- Versioned, encrypted S3 remote state with native S3 locking
- Two-Availability-Zone VPC
- Public, private application and isolated database subnets
- Cost-aware single or per-AZ NAT gateway configuration
- Private, versioned document storage with TLS-only access
- Encrypted Amazon RDS for PostgreSQL
- AWS Budgets alerts and Cost Anomaly Detection
- GitHub Actions formatting and validation workflow

Application compute, CloudFront, Cognito, queues and deployment roles are intentionally the next layer. This first layer establishes the network, data and cost-control foundation they require.

## Prerequisites

- Terraform 1.15.9
- AWS CLI v2
- An AWS account with MFA-protected administrative access
- Africa (Cape Town), `af-south-1`, enabled if selected
- A unique state bucket name
- A verified billing-alert email address

Do not use root-user credentials or long-lived AWS access keys.

## Repository structure

```text
infra/
  bootstrap/              Remote-state bucket, created once
  modules/
    network/              VPC, subnets, routing and application security group
    storage/              Private customer/vehicle document bucket
    database/             PostgreSQL and its security group
    cost-controls/        Budget and anomaly notifications
  stacks/foundation/      Composes the reusable modules
  environments/
    demo/                 Zero-funding serverless booking demonstration
    nonprod/              Reduced-cost integration/staging foundation
    production/           Production safety defaults
scripts/
  terraform-check.ps1     Local formatting and validation helper
```

## 1. Bootstrap remote state

Skip this section for the zero-funding demo. The demo uses local state to avoid creating an additional cloud resource.

Copy `infra/bootstrap/terraform.tfvars.example` to `terraform.tfvars`, choose a globally unique bucket name, authenticate with temporary AWS credentials, then run:

```powershell
Set-Location infra/bootstrap
terraform init
terraform plan -out bootstrap.tfplan
terraform apply bootstrap.tfplan
```

The bootstrap state starts locally because the remote bucket does not exist yet. Store that small local state securely, then migrate it deliberately if required.

## 2. Configure an environment

For non-production, copy both examples:

```powershell
Copy-Item infra/environments/nonprod/backend.hcl.example infra/environments/nonprod/backend.hcl
Copy-Item infra/environments/nonprod/terraform.tfvars.example infra/environments/nonprod/terraform.tfvars
```

Fill in the state bucket, AWS account ID and billing email. Then:

```powershell
Set-Location infra/environments/nonprod
terraform init -backend-config=backend.hcl
terraform validate
terraform plan -out nonprod.tfplan
```

Review the plan and projected cost before any apply. Repeat with `production` only after non-production tests pass.

## Zero-funding demo deployment

Copy the example variables and replace the placeholders:

```powershell
Copy-Item infra/environments/demo/terraform.tfvars.example infra/environments/demo/terraform.tfvars
./scripts/build-demo-package.ps1
Set-Location infra/environments/demo
terraform init
terraform plan -out demo.tfplan
```

Review the plan carefully. It should contain no VPC, NAT Gateway, load balancer, ECS service or RDS database. Apply only while using the AWS Free plan or after accepting the small pay-as-you-go risk:

```powershell
terraform apply demo.tfplan
terraform output -raw demo_url
```

Destroy the demo when it is no longer needed:

```powershell
terraform destroy
```

## Required decisions before deployment

- Confirm `af-south-1` or replace it after the documented latency comparison.
- Confirm the AWS account IDs.
- Approve the monthly budget thresholds.
- Confirm whether production starts with Single-AZ or Multi-AZ RDS.
- Confirm whether one or two NAT gateways are approved.
- Agree the database name and retention requirements.

## Security notes

- The RDS instance has no public endpoint.
- The document bucket blocks all public access and denies non-TLS requests.
- Database credentials are generated and managed by RDS in Secrets Manager.
- Terraform state is sensitive; restrict read access as tightly as write access.
- Production deletion protection is enabled in the example variables.

## Validation

Run:

```powershell
./scripts/terraform-check.ps1
```

The helper requires Terraform to be installed. GitHub Actions performs the same formatting and validation checks on pushes and pull requests.
