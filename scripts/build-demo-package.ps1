$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$demoRoot = Join-Path $repositoryRoot "infra/environments/demo"
$source = Join-Path $demoRoot "app/handler.py"
$archive = Join-Path $demoRoot "luxury-rental-demo.zip"

if (-not (Test-Path -LiteralPath $source)) {
    throw "Lambda source file was not found: $source"
}

Compress-Archive -LiteralPath $source -DestinationPath $archive -CompressionLevel Optimal -Force
Write-Output "Created $archive"

