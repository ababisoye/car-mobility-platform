$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$demoRoot = Join-Path $repositoryRoot "infra/environments/demo"
$source = @(
    (Join-Path $demoRoot "app/handler.py"),
    (Join-Path $demoRoot "app/openapi.json")
)
$archive = Join-Path $demoRoot "luxury-rental-demo.zip"

foreach ($sourceFile in $source) {
    if (-not (Test-Path -LiteralPath $sourceFile)) {
        throw "Lambda source file was not found: $sourceFile"
    }
}

Compress-Archive -LiteralPath $source -DestinationPath $archive -CompressionLevel Optimal -Force
Write-Output "Created $archive"
