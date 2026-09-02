# CI/CD supply-chain controls

Every external GitHub Action is pinned to a full 40-character commit SHA. A nearby major-version comment keeps each workflow readable while preventing a mutable tag from changing the executed code without a repository commit.

`tests/test_ci_supply_chain.py` fails when:

- an external action uses a branch or version tag instead of a commit;
- a pinned action omits its readable major-version comment;
- a workflow lacks the default `contents: read` permission;
- validation receives an OIDC token permission;
- a workflow grants write access to contents, actions, pull requests or packages;
- the release workflow grants `id-token: write` outside its single protected release job.

Dependabot checks GitHub Actions and all five Terraform roots weekly. Its pull requests still pass through the same test and Terraform validation workflow; updates are never deployed automatically.

## Updating a pin

Review the upstream release notes and repository ownership, confirm the tag's commit through the official GitHub repository, update the SHA and version comment, and let CI validate the change. The controlled release environment remains a separate manual approval boundary.
