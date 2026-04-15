param(
  [string]$RepoRoot,
  [string]$Tag = "v2.0.0-final",
  [string]$TargetCommitish = "main",
  [string]$ReleaseName = "Project A v2.0.0-final",
  [string]$BodyFile,
  [switch]$Draft,
  [switch]$Prerelease,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

if (-not $BodyFile) {
  $BodyFile = Join-Path $RepoRoot "docs\projectA_release_note_v2.0.0-final.md"
}

function Resolve-RepoInfo {
  param([string]$Root)
  $url = (git -C $Root config --get remote.origin.url).Trim()
  if (-not $url) {
    throw "Cannot resolve remote.origin.url"
  }

  if ($url -match 'github\.com[:/](?<owner>[^/]+)/(?<repo>[^/.]+)(\.git)?$') {
    return @{ owner = $Matches.owner; repo = $Matches.repo; url = $url }
  }

  throw "Unsupported remote URL format: $url"
}

function Get-Token {
  if ($env:GH_TOKEN) { return $env:GH_TOKEN }
  if ($env:GITHUB_TOKEN) { return $env:GITHUB_TOKEN }
  return $null
}

function Read-Body {
  param([string]$Path)
  if (-not (Test-Path $Path)) {
    throw "Release body file not found: $Path"
  }
  $resolved = (Resolve-Path -LiteralPath $Path).Path
  return [System.IO.File]::ReadAllText($resolved, [System.Text.Encoding]::UTF8)
}

$repoInfo = Resolve-RepoInfo -Root $RepoRoot
$owner = $repoInfo.owner
$repo = $repoInfo.repo
$baseApi = "https://api.github.com/repos/$owner/$repo"
$bodyText = Read-Body -Path $BodyFile

Write-Host "Repo: $owner/$repo" -ForegroundColor Cyan
Write-Host "Tag : $Tag" -ForegroundColor Cyan
Write-Host "Body: $BodyFile" -ForegroundColor Cyan

$payload = @{
  tag_name = $Tag
  target_commitish = $TargetCommitish
  name = $ReleaseName
  body = $bodyText
  draft = [bool]$Draft
  prerelease = [bool]$Prerelease
}

if ($DryRun) {
  Write-Host "" 
  Write-Host "[DRY RUN] Would create/update release with payload:" -ForegroundColor Yellow
  $payload | ConvertTo-Json -Depth 10
  exit 0
}

$token = Get-Token
if (-not $token) {
  Write-Host "" 
  Write-Host "Missing GH_TOKEN/GITHUB_TOKEN. Set one token and rerun." -ForegroundColor Red
  Write-Host "Example:" -ForegroundColor Yellow
  Write-Host "  `$env:GITHUB_TOKEN='YOUR_PAT'" -ForegroundColor Yellow
  $quotedPath = '"' + $PSCommandPath + '"'
  Write-Host "  powershell -ExecutionPolicy Bypass -File $quotedPath" -ForegroundColor Yellow
  exit 2
}

$headers = @{
  Authorization = "Bearer $token"
  Accept = "application/vnd.github+json"
  "X-GitHub-Api-Version" = "2022-11-28"
}

$existing = $null
try {
  $existing = Invoke-RestMethod -Method Get -Uri "$baseApi/releases/tags/$Tag" -Headers $headers
} catch {
  $status = $null
  if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
    $status = [int]$_.Exception.Response.StatusCode
  }
  if ($status -ne 404) {
    throw
  }
}

if ($existing -and $existing.id) {
  $id = $existing.id
  $result = Invoke-RestMethod -Method Patch -Uri "$baseApi/releases/$id" -Headers $headers -ContentType "application/json" -Body ($payload | ConvertTo-Json -Depth 10)
  Write-Host "Updated release: $($result.html_url)" -ForegroundColor Green
} else {
  $result = Invoke-RestMethod -Method Post -Uri "$baseApi/releases" -Headers $headers -ContentType "application/json" -Body ($payload | ConvertTo-Json -Depth 10)
  Write-Host "Created release: $($result.html_url)" -ForegroundColor Green
}
