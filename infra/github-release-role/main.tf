data "aws_iam_policy_document" "github_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${var.github_environment}"]
    }
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

resource "aws_iam_role" "github_release" {
  name               = "luxury-rental-github-release"
  description        = "Short-lived GitHub OIDC identity for controlled Lambda releases."
  assume_role_policy = data.aws_iam_policy_document.github_trust.json
}

data "aws_iam_policy_document" "release" {
  statement {
    sid = "InspectAndReleaseDemoLambda"
    actions = [
      "lambda:GetAlias",
      "lambda:GetFunction",
      "lambda:PublishVersion",
      "lambda:UpdateAlias",
      "lambda:UpdateFunctionCode",
    ]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:luxury-rental-demo",
      "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:luxury-rental-demo:*",
    ]
  }
}

resource "aws_iam_role_policy" "release" {
  name   = "lambda-version-promotion"
  role   = aws_iam_role.github_release.id
  policy = data.aws_iam_policy_document.release.json
}
