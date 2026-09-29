# GMEE V2 — live end-to-end verification sweep for the new API surface.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\verify_endpoints.ps1
#
# Checks the endpoints added by the eval / alerts / lineage / simulate work
# against a RUNNING backend (default http://127.0.0.1:8000) and writes
# _endpoint_report.txt next to this script.
#
# Sample IDs for the DB/Neo4j-backed probes are discovered automatically:
#   - lineage  -> a claim that really has an EVOLVED_FROM edge (Postgres)
#   - feedback -> any claim (Postgres)
#   - hub      -> an article present in the SIMILAR graph (Neo4j HTTP, dev)
# Discovery can be bypassed by dropping the id into _hub.txt /
# _lineage_claim.txt / _feedback_claim.txt (one id per file).
[CmdletBinding()]
param(
    [string]$Base = 'http://127.0.0.1:8000/api/v1',
    [string]$PgContainer = 'gmee_postgres',
    [string]$PgDatabase = 'gmee_v2',
    [int]$Neo4jHttpPort = 7475
)

$ErrorActionPreference = 'Continue'
$log = @()

function Clean-Id {
    param([string]$Raw)
    if (-not $Raw) { return $null }
    return (($Raw | Select-Object -First 1) -replace '[^0-9a-fA-F-]', '')
}

function From-File {
    param([string]$Name)
    $path = Join-Path $PSScriptRoot $Name
    if (-not (Test-Path $path)) { return $null }
    return Clean-Id (Get-Content $path -First 1)
}

function From-Db {
    param([string]$Sql)
    try {
        $raw = docker exec $PgContainer psql -U postgres -d $PgDatabase -t -A -c $Sql 2>$null
        return Clean-Id $raw
    }
    catch { return $null }
}

function From-Neo4j {
    $envFile = Join-Path (Split-Path $PSScriptRoot -Parent) '.env'
    $password = 'password'
    if (Test-Path $envFile) {
        $line = Select-String -Path $envFile -Pattern '^NEO4J_PASSWORD=' | Select-Object -First 1
        if ($line) { $password = ($line.Line -split '=', 2)[1].Trim() }
    }
    $auth = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("neo4j:$password"))
    $body = '{"statements":[{"statement":"MATCH (a:Article)-[r:SIMILAR]-() RETURN a.id AS id, count(r) AS deg ORDER BY deg DESC LIMIT 1"}]}'
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Neo4jHttpPort/db/neo4j/tx/commit" -Method Post `
            -Headers @{ Authorization = "Basic $auth" } -ContentType 'application/json' -Body $body -TimeoutSec 30
        return Clean-Id $r.results[0].data[0].row[0]
    }
    catch { return $null }
}

function Probe {
    param([string]$Label, [string]$Path, [string]$Method = 'GET', [string]$Body = $null)
    try {
        $req = @{ Uri = "$Base$Path"; Method = $Method; TimeoutSec = 180; UseBasicParsing = $true }
        if ($Body) { $req.Body = $Body; $req.ContentType = 'application/json' }
        $r = Invoke-WebRequest @req
        $flat = ($r.Content -replace '\s+', ' ')
        $script:log += "[$Method] $Label -> $($r.StatusCode) ($($r.RawContentLength) bytes)"
        $script:log += "    $($flat.Substring(0, [Math]::Min(600, $flat.Length)))"
    }
    catch {
        $resp = $_.Exception.Response
        $code = if ($resp) { [int]$resp.StatusCode } else { 'n/a' }
        $script:log += "[$Method] $Label -> ERROR $code $($_.Exception.Message)"
    }
}

# ---------------------------------------------------------------------------
# sample ids
# ---------------------------------------------------------------------------
$lineageClaim = From-File '_lineage_claim.txt'
if (-not $lineageClaim) {
    $lineageClaim = From-Db "select from_claim_id::text from claim_relationships where relationship_type='EVOLVED_FROM' limit 1;"
}
$feedbackClaim = From-File '_feedback_claim.txt'
if (-not $feedbackClaim) { $feedbackClaim = From-Db 'select id::text from claims limit 1;' }
$hub = From-File '_hub.txt'
if (-not $hub) { $hub = From-Neo4j }

$log += "ids: lineage=$lineageClaim feedback=$feedbackClaim hub=$hub"

# ---------------------------------------------------------------------------
# read-only probes
# ---------------------------------------------------------------------------
Probe 'health'              '/health'
Probe 'alerts'              '/alerts'
Probe 'eval/progress'       '/eval/progress'
Probe 'eval/next (blinded)' '/eval/next?annotator=verify-script'
Probe 'verdicts/stats'      '/verdicts/stats'
Probe 'verdicts/summary'    '/verdicts/summary'
if ($lineageClaim) {
    Probe 'graph/lineage (has lineage)' "/graph/lineage/$lineageClaim"
    Probe 'graph/lineage (no lineage)'  "/graph/lineage/$feedbackClaim"
}
else { $log += 'graph/lineage -> SKIPPED (no claim id)' }
Probe 'graph/lineage (bad uuid)' '/graph/lineage/not-a-uuid'
if ($hub) { Probe 'graph/simulate' "/graph/simulate?hub=$hub&p=0.5&max_depth=3" }
else { $log += 'graph/simulate -> SKIPPED (hub not in link graph / Neo4j unreachable)' }

# ---------------------------------------------------------------------------
# write-path probe (idempotent upserts; safe to re-run)
# ---------------------------------------------------------------------------
if ($feedbackClaim) {
    Probe 'verdicts/feedback (POST)' '/verdicts/feedback' 'POST' `
        ('{"claim_id":"' + $feedbackClaim + '","vote":"AGREE","comment":"verify_endpoints.ps1"}')
}

# ---------------------------------------------------------------------------
# route inventory
# ---------------------------------------------------------------------------
try {
    $spec = Invoke-RestMethod 'http://127.0.0.1:8000/openapi.json' -TimeoutSec 60
    $paths = $spec.paths.PSObject.Properties.Name | Where-Object { $_ -match 'eval|alert|lineage|simulate|feedback' } | Sort-Object
    $log += "ROUTES MATCHING eval|alert|lineage|simulate|feedback ($($paths.Count)):"
    foreach ($p in $paths) {
        $log += "    $(($spec.paths.$p.PSObject.Properties.Name -join ',').ToUpper()) $p"
    }
}
catch { $log += "openapi -> ERROR $($_.Exception.Message)" }

$log -join "`n" | Set-Content -Encoding utf8 (Join-Path $PSScriptRoot '_endpoint_report.txt')
$log -join "`n"
