# Analiza un componente UI de MATLAB R2026b con REA y guarda la evidencia JSON.
# Uso: analyze-component.ps1 -Component mw-taskbar [-ExtraArgs @('--analysis-timeout-ms','600000')]
param(
    [Parameter(Mandatory = $true)][string]$Component,
    [int]$MaxHeapMb = 0,
    [int]$AnalysisTimeoutMs = 0,
    [string]$ReaRoot = "C:\Program Files\MATLAB\R2026b\ui",
    [string]$OutDir = "C:\Users\dav\matlab-clone\rea\ui-analysis"
)

$rea = "C:\Users\dav\AppData\Local\npm-cache\_npx\ad9a3fdbcad992c6\node_modules\.bin\rea.cmd"
$target = Join-Path $ReaRoot $Component
$out = Join-Path $OutDir "$Component.json"
$err = Join-Path $OutDir "$Component.err"

if (-not (Test-Path $target)) { throw "Target not found: $target" }

$args = @("analyze-javascript-application", "`"$target`"", "--format", "json")
if ($MaxHeapMb -gt 0) { $args += @("--max-heap-mb", "$MaxHeapMb") }
if ($AnalysisTimeoutMs -gt 0) { $args += @("--analysis-timeout-ms", "$AnalysisTimeoutMs") }
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath $rea -ArgumentList $args -RedirectStandardOutput $out -RedirectStandardError $err -NoNewWindow -Wait -PassThru
$sw.Stop()
[PSCustomObject]@{
    Component = $Component
    ExitCode  = $p.ExitCode
    Seconds   = [math]::Round($sw.Elapsed.TotalSeconds, 1)
    OutBytes  = (Get-Item $out).Length
    ErrBytes  = (Get-Item $err).Length
} | Format-List
