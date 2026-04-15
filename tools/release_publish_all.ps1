param(
  [string]$RepoRoot,
  [string]$Tag = "v2.0.0-final",
  [switch]$OverwriteAssets,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$publishScript = Join-Path $PSScriptRoot "publish_github_release.ps1"
if (-not (Test-Path -LiteralPath $publishScript)) {
  throw "publish script not found: $publishScript"
}

$params = @{
  RepoRoot = $RepoRoot
  Tag = $Tag
  UploadAssets = $true
  AutoAssets = $true
}

if ($OverwriteAssets) {
  $params.OverwriteAssets = $true
}
if ($DryRun) {
  $params.DryRun = $true
}

& $publishScript @params
