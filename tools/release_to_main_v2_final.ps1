param(
  [string]$RepoRoot = "D:\codex\project A",
  [string]$SourceBranch = "codex/w25q128-integration",
  [string]$MainBranch = "main",
  [string]$Tag = "v2.0.0-final",
  [switch]$Execute
)

$ErrorActionPreference = "Stop"

function Step([string]$Name, [string]$Cmd) {
  Write-Host ""
  Write-Host "=== $Name ===" -ForegroundColor Cyan
  Write-Host $Cmd -ForegroundColor Yellow
  if ($Execute) { Invoke-Expression $Cmd }
}

Step "Fetch" "git -C `"$RepoRoot`" fetch --all --prune"
Step "Source Branch Check" "git -C `"$RepoRoot`" checkout $SourceBranch"
Step "Source Status" "git -C `"$RepoRoot`" status --short"
Step "Main Checkout" "git -C `"$RepoRoot`" checkout $MainBranch"
Step "Main Pull" "git -C `"$RepoRoot`" pull --ff-only origin $MainBranch"
Step "Merge Release" "git -C `"$RepoRoot`" merge --no-ff $SourceBranch -m `"release(projectA): merge v2.0.0-final showcase`""
Step "Tag" "git -C `"$RepoRoot`" tag -a $Tag -m `"Project A final full-chain release`""
Step "Push Main" "git -C `"$RepoRoot`" push origin $MainBranch"
Step "Push Tag" "git -C `"$RepoRoot`" push origin $Tag"

Write-Host ""
if ($Execute) {
  Write-Host "[DONE] Release merge executed." -ForegroundColor Green
} else {
  Write-Host "[DONE] Dry-run commands printed. Add -Execute to run." -ForegroundColor Green
}
