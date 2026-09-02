$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot

$terraformCommand = Get-Command terraform -ErrorAction SilentlyContinue
if (-not $terraformCommand) {
    throw "Terraform is not installed or is not available on PATH. Install Terraform 1.15.9 and retry."
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    throw "Python is not installed or is not available on PATH. Install Python 3.13 and retry."
}

$requiredVersion = "Terraform v1.15.9"
$actualVersion = (& $terraformCommand.Source version | Select-Object -First 1)
if ($actualVersion -ne $requiredVersion) {
    throw "Expected $requiredVersion but found $actualVersion."
}

Push-Location $repositoryRoot
try {
    & $pythonCommand.Source -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "Python tests failed with exit code $LASTEXITCODE."
    }

    & $terraformCommand.Source fmt -check -recursive infra
    if ($LASTEXITCODE -ne 0) {
        throw "Terraform formatting failed with exit code $LASTEXITCODE."
    }

    & (Join-Path $PSScriptRoot "build-demo-package.ps1")

    $roots = @(
        "infra/bootstrap",
        "infra/environments/demo",
        "infra/environments/nonprod",
        "infra/environments/production",
        "infra/github-release-role"
    )

    foreach ($root in $roots) {
        Push-Location (Join-Path $repositoryRoot $root)
        try {
            & $terraformCommand.Source init -backend=false -input=false
            if ($LASTEXITCODE -ne 0) {
                throw "Terraform initialization failed for $root with exit code $LASTEXITCODE."
            }

            & $terraformCommand.Source validate
            if ($LASTEXITCODE -ne 0) {
                throw "Terraform validation failed for $root with exit code $LASTEXITCODE."
            }
        }
        finally {
            Pop-Location
        }
    }

    Write-Output "Project verification passed. No infrastructure plan or deployment was run."
}
finally {
    Pop-Location
}
