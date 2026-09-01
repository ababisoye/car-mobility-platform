$ErrorActionPreference = "Stop"

if (-not (Get-Command terraform -ErrorAction SilentlyContinue)) {
    throw "Terraform is not installed or is not available on PATH. Install Terraform 1.15.9 and retry."
}

$requiredVersion = "Terraform v1.15.9"
$actualVersion = (terraform version | Select-Object -First 1)
if ($actualVersion -ne $requiredVersion) {
    throw "Expected $requiredVersion but found $actualVersion."
}

terraform fmt -check -recursive

& (Join-Path $PSScriptRoot "build-demo-package.ps1")

$roots = @(
    "infra/bootstrap",
    "infra/environments/demo",
    "infra/environments/nonprod",
    "infra/environments/production"
)

foreach ($root in $roots) {
    Push-Location $root
    try {
        terraform init -backend=false -input=false
        terraform validate
    }
    finally {
        Pop-Location
    }
}
