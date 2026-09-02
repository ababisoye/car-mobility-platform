# Zero-funding architecture policy

The demo's cost claims are enforced by `tests/test_zero_funding_policy.py`, which runs in the existing GitHub Actions validation workflow.

The policy currently requires:

- an explicit allowlist of Lambda, DynamoDB, CloudWatch Logs, IAM and AWS Budgets resource types;
- exactly six DynamoDB tables at one provisioned read and write capacity unit each;
- a 128 MB ARM Lambda with a five-second timeout and reserved concurrency of one;
- one-day log retention;
- a USD 1 actual and forecast budget alert threshold;
- a Lambda Function URL as the only public entry point;
- no wildcard IAM actions or resource grants.

Because the allowlist excludes them, adding a NAT Gateway, load balancer, API Gateway, RDS database, container service, Kubernetes cluster, cache, search domain or S3 bucket fails CI. This does not prove that AWS usage can never create a charge: budgets are alerts, requests consume service quotas, and AWS pricing or free-plan terms may change.

## Changing the policy

A deliberate architecture change may update the test, but the same pull request should include:

1. the business reason for the new service or higher limit;
2. a current AWS pricing estimate and expected traffic;
3. revised budget and shutdown controls;
4. updated architecture and operations documentation;
5. explicit approval before deployment.

Run the policy locally with:

```powershell
python -m unittest discover -s tests -p "test_zero_funding_policy.py" -v
```
