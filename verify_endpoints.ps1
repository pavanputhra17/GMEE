# Read-only HTTP contract verification, NOT browser E2E.
# No database discovery, .env reading, labels, feedback or authorized triggers.
# Optional bearer token: set GMEE_VERIFY_TOKEN in the process environment.
[CmdletBinding()]
param(
    [string]$Base = 'http://127.0.0.1:8000/api/v1',
    [ValidateRange(1, 15)][int]$TimeoutSec = 8,
    [ValidateRange(10, 240)][int]$DeadlineSec = 120,
    [string]$ReportPath
)

$runner = Join-Path $PSScriptRoot 'infra/scripts/read_only_sweep.ps1'
& $runner -Mode Endpoints -Base $Base -TimeoutSec $TimeoutSec -DeadlineSec $DeadlineSec -ReportPath $ReportPath
exit $LASTEXITCODE
