param(
    [string]$Message
)

$ErrorActionPreference = "Stop"

$root = git rev-parse --show-toplevel 2>$null
if (-not $root) {
    throw "This script must be run inside a Git repository."
}

Set-Location $root

git update-index -q --refresh
$status = git status --short
if (-not $status) {
    Write-Host "No changes to sync."
    exit 0
}

git add -A

$staged = git diff --cached --name-only
if (-not $staged) {
    Write-Host "No staged changes to sync."
    exit 0
}

if (-not $Message) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $Message = "chore: auto sync $stamp"
}

git commit -m $Message

# The post-commit hook normally pushes. This fallback helps if hooks are disabled.
$branch = git branch --show-current
if ($branch) {
    git push -u origin $branch
}
