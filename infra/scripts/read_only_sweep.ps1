# Shared, bounded read-only HTTP sweep. Compatible with Windows PowerShell 5.1.
[CmdletBinding()]
param(
    [ValidateSet('Endpoints', 'UI')][string]$Mode = 'Endpoints',
    [string]$Base = 'http://127.0.0.1:8000/api/v1',
    [ValidateRange(1, 15)][int]$TimeoutSec = 8,
    [ValidateRange(10, 240)][int]$DeadlineSec = 120,
    [string]$ReportPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$baseUri = $null
if (-not [Uri]::TryCreate($Base, [UriKind]::Absolute, [ref]$baseUri) -or
    $baseUri.Scheme -notin @('http', 'https') -or $baseUri.UserInfo -or
    $baseUri.Query -or $baseUri.Fragment -or $baseUri.AbsolutePath.TrimEnd('/') -ne '/api/v1') {
    Write-Error 'Base must be an HTTP(S) API origin ending in /api/v1, without credentials.'
    exit 2
}
$Base = $Base.TrimEnd('/')
$token = [Environment]::GetEnvironmentVariable('GMEE_VERIFY_TOKEN')
$clock = [Diagnostics.Stopwatch]::StartNew()
$log = New-Object 'System.Collections.Generic.List[string]'
$fails = 0

function Probe {
    param(
        [string]$Label,
        [string]$Path,
        [string[]]$Required = @(),
        [int[]]$Status = @(200),
        [ValidateSet('GET', 'POST')][string]$Method = 'GET',
        [hashtable]$Body,
        [switch]$Anonymous
    )
    $remaining = $DeadlineSec - $clock.Elapsed.TotalSeconds
    if ($remaining -le 0) {
        $script:fails++
        $log.Add("[FAIL] $Label -> overall deadline exceeded")
        return $null
    }
    $headers = @{ Accept = 'application/json' }
    if ($token -and -not $Anonymous) { $headers.Authorization = "Bearer $token" }
    $request = @{
        Uri = "$Base$Path"
        Method = $Method
        Headers = $headers
        TimeoutSec = [Math]::Max(1, [Math]::Min($TimeoutSec, [Math]::Ceiling($remaining)))
        UseBasicParsing = $true
        MaximumRedirection = 0
        ErrorAction = 'Stop'
    }
    if ($null -ne $Body) {
        $request.ContentType = 'application/json'
        $request.Body = $Body | ConvertTo-Json -Compress
    }
    $code = 0
    $json = $null
    try {
        $response = Invoke-WebRequest @request
        $code = [int]$response.StatusCode
        if ($Required.Count -gt 0 -or ($code -eq 200 -and $Path -like '/eval/next*')) {
            $json = $response.Content | ConvertFrom-Json
        }
    }
    catch {
        if ($_.Exception.PSObject.Properties['Response'] -and $_.Exception.Response) {
            $code = [int]$_.Exception.Response.StatusCode
        }
        # Do not print exception messages, request headers, tokens or response bodies.
    }
    if ($Status -notcontains $code) {
        $script:fails++
        $log.Add("[FAIL] $Label -> HTTP $code; expected $($Status -join '/')")
        return $null
    }
    if ($Required.Count -gt 0) {
        if ($null -eq $json) {
            $script:fails++
            $log.Add("[FAIL] $Label -> expected a JSON object")
            return $null
        }
        $missing = @($Required | Where-Object { $null -eq $json.PSObject.Properties[$_] })
        if ($missing.Count -gt 0) {
            $script:fails++
            $log.Add("[FAIL] $Label -> missing fields: $($missing -join ', ')")
            return $null
        }
    }
    $log.Add("[PASS] $Label -> HTTP $code")
    return $json
}

$readiness = Probe 'readiness' '/health/ready' @('postgres', 'neo4j', 'redis', 'status')
if ($readiness -and ($readiness.status -ne 'ready' -or $readiness.postgres -ne 'ok' -or
    $readiness.neo4j -ne 'ok' -or $readiness.redis -ne 'ok')) {
    $script:fails++
    $log.Add('[FAIL] readiness -> all datastores must be ready')
}
$null = Probe 'liveness' '/health' @('status')
$null = Probe 'corpus stats' '/corpus/stats' @('total', 'embedded', 'domains', 'nlp_counts')
$null = Probe 'corpus articles (empty is valid)' '/corpus/articles?limit=5&offset=0' @('total', 'items', 'domains')
$null = Probe 'verdict stats' '/verdicts/stats' @('total_claims', 'distribution', 'outlets')
$null = Probe 'claims graph' '/graph/claims?limit=40' @('nodes', 'edges', 'counts', 'edge_source')

# Every POST below is either unauthenticated and required to fail authorization,
# or the non-persisting authenticated text-comparison API. No scientific writes.
foreach ($path in @('/collection/trigger', '/preprocessing/trigger', '/nlp/trigger', '/evolution/trigger', '/alerts/evaluate')) {
    $null = Probe "$path anonymous admin gate" $path -Status @(401, 403) -Method POST -Body @{} -Anonymous
}
$evidence = @{ claim_text = 'The fixture agency reported 10 cases.'; limit = 1 }
$null = Probe 'evidence auth gate' '/verdicts/check' -Status @(401, 403) -Method POST -Body $evidence -Anonymous
$comparison = @{ older_text = 'The agency found 10 survivors.'; newer_text = 'The agency found 12 survivors.' }
$null = Probe 'mutation auth gate' '/graph/mutation/compare' -Status @(401, 403) -Method POST -Body $comparison -Anonymous
$null = Probe 'eval auth gate' '/eval/next' -Status @(401, 403) -Anonymous

if ($token) {
    $null = Probe 'current user' '/auth/me' @('id', 'email', 'role')
    $analysis = Probe 'read-only typed mutation comparison' '/graph/mutation/compare' @('analysis') -Method POST -Body $comparison
    if ($analysis) {
        $details = $analysis.analysis
        if ($null -eq $details.PSObject.Properties['observed_propagation'] -or
            $details.observed_propagation -ne $false -or
            $null -eq $details.PSObject.Properties['mutation_types'] -or
            $details.mutation_types -notcontains 'NUMERIC_DRIFT') {
            $script:fails++
            $log.Add('[FAIL] mutation comparison -> missing numeric typing or causal disclaimer')
        }
    }
    $pair = Probe 'blinded evaluation next (no labeling)' '/eval/next' @('done')
    if ($pair -and -not $pair.done) {
        if ($null -eq $pair.PSObject.Properties['pair']) {
            $script:fails++
            $log.Add('[FAIL] eval next -> missing pair')
        }
        else {
            $cues = @('verdict', 'score', 'bucket', 'similarity', 'stance', 'sim_score')
            $leaks = @($pair.pair.PSObject.Properties.Name | Where-Object { $cues -contains $_ })
            if ($leaks.Count -gt 0) {
                $script:fails++
                $log.Add('[FAIL] eval next -> annotation cues leaked')
            }
        }
    }
}
else {
    $null = Probe 'current user anonymous gate' '/auth/me' -Status @(401, 403) -Anonymous
    $log.Add('[INFO] Authenticated comparisons require GMEE_VERIFY_TOKEN; this read-only sweep is not the fixture E2E gate')
}

if ($Mode -eq 'UI') {
    $checks = @(
        @('/dashboard', @('services', 'generated_at')),
        @('/verdicts?limit=5', @('total', 'items')),
        @('/verdicts/summary', @('engine_config', 'distribution')),
        @('/corpus/articles/recent?limit=5', @('items')),
        @('/corpus/graph/story-clusters?min_links=3&limit=4', @('clusters')),
        @('/graph/full', @('nodes', 'edges', 'counts')),
        @('/graph/timeline?limit=5', @('clusters', 'count')),
        @('/graph/scoops?limit=5', @('races', 'count')),
        @('/verdicts/game/mutations?min_versions=2&limit=5', @('chains')),
        @('/alerts', @('alerts', 'stats', 'generated_at')),
        @('/alerts/feed?limit=5', @('items', 'counts', 'generated_at'))
    )
    foreach ($check in $checks) { $null = Probe $check[0] $check[0] $check[1] }
    if ($token) {
        $null = Probe 'eval progress' '/eval/progress' @('total_pairs', 'by_bucket', 'per_annotator', 'inter_annotator', 'complete')
    }
}

$log.Add("RESULT: $fails failures; read-only HTTP checks, no browser assertions")
$log -join "`n" | Write-Output
if ($ReportPath) {
    try {
        # Never overwrite the user's existing verification artifacts.
        $log -join "`n" | Out-File -FilePath $ReportPath -Encoding utf8 -NoClobber
    }
    catch {
        Write-Error 'Report path already exists or cannot be written; no report was overwritten.'
        exit 1
    }
}
if ($fails -gt 0) { exit 1 }
exit 0
