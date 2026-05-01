param(
    [int]$QuietSeconds = 10,
    [int]$PollSeconds = 2
)

$ErrorActionPreference = "Stop"

$root = git rev-parse --show-toplevel 2>$null
if (-not $root) {
    throw "This script must be run inside a Git repository."
}

Set-Location $root
Write-Host "Watching $root"
Write-Host "Changes will be committed and pushed after $QuietSeconds quiet seconds."

$lastState = ""
$lastChangeAt = Get-Date

while ($true) {
    git update-index -q --refresh
    $state = (git status --short) -join "`n"

    if ($state -ne $lastState) {
        $lastState = $state
        $lastChangeAt = Get-Date
    }

    if ($state -and ((Get-Date) - $lastChangeAt).TotalSeconds -ge $QuietSeconds) {
        . "$PSScriptRoot\git-auto-sync.ps1"
        $lastState = ""
        $lastChangeAt = Get-Date
    }

    Start-Sleep -Seconds $PollSeconds
}
