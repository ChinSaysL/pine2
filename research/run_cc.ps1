param([string]$From = "2010.06.01", [string]$To = "2026.10.01")
# Local Strategy Tester A/B of the minimum-close-penetration rule (InpCloseMinAtr).
# The experiment EA is compiled under MQL5\Experts\GTBExperiment - the deployed EA and presets are untouched.
#
# Research profile (identical for every variant, so only the entry rule differs):
#   risk fixed 1%, loss limits raised out of the way (the EA's 2.5%/5% guards stop trading for good
#   once the total limit is touched, which would truncate a backtest that starts at the initial balance),
#   a fresh magic per variant so no stale 'limitStop' global variable is inherited.
$r = "C:\Users\Abdo\Downloads\pine2\research"
Start-Transcript -Path "$r\cc_run.log" -Append | Out-Null
"### run_cc started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  window $From .. $To  (fixed 1% risk, limits 50/50, fresh magic)"
$tf = "$env:APPDATA\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075"
$expDir = "$tf\MQL5\Experts\GTBExperiment"
$terminal = Join-Path $env:ProgramFiles "MetaTrader 5\terminal64.exe"
$editor = Join-Path $env:ProgramFiles "MetaTrader 5\MetaEditor64.exe"
$common = Join-Path $env:APPDATA "MetaQuotes\Terminal\Common\Files\GoldBreakout"

"=== install + compile the experiment EA"
New-Item -ItemType Directory -Force -Path $expDir | Out-Null
Copy-Item "$r\ea\GTBClosePen.mq5" "$expDir\GTBClosePen.mq5" -Force
Remove-Item "$expDir\GTBClosePen.ex5" -ErrorAction SilentlyContinue
Start-Process $editor -ArgumentList "/compile:`"$expDir\GTBClosePen.mq5`"", "/log:`"$expDir\compile.log`"" -Wait | Out-Null
for ($i = 0; $i -lt 60 -and -not (Test-Path "$expDir\GTBClosePen.ex5"); $i++) { Start-Sleep -Seconds 2 }
if (-not (Test-Path "$expDir\GTBClosePen.ex5")) {
    "COMPILE FAILED"
    if (Test-Path "$expDir\compile.log") { Get-Content "$expDir\compile.log" }
    Stop-Transcript | Out-Null
    exit 1
}
"compiled GTBClosePen.ex5: " + (Get-Item "$expDir\GTBClosePen.ex5").Length + " bytes"

function Build([string]$pen, [int]$magic) {
    $lines = @(([IO.File]::ReadAllText("$r\live_inputs.txt") -replace "`r`n", "`n").Split("`n") | Where-Object { $_ -match '=' })
    foreach ($pair in @("InpBadMode=1", "InpBadRiskMult=0.5", "InpCloseMinAtr=$pen",
                        "InpRiskMode=0", "InpRiskPercent=1.0", "InpDailyLimitPct=50", "InpTotalLimitPct=50",
                        "InpMagic=$magic")) {
        $k = $pair.Split("=")[0]
        $lines = @($lines | Where-Object { $_.Split("=")[0] -ne $k })
        $lines += $pair
    }
    $lines -join "`n"
}
$variants = [ordered]@{ "off" = "-1"; "p000" = "0.0"; "p010" = "0.10"; "p015" = "0.15"; "p025" = "0.25"; "p040" = "0.40"; "p060" = "0.60" }
$idx = 0
foreach ($k in $variants.Keys) {
    $name = "cc_$k"
    $magic = 24240100 + $idx; $idx++
    $ini = "[Tester]`nExpert=GTBExperiment\GTBClosePen.ex5`nSymbol=XAUUSD`nPeriod=H1`nOptimization=0`nModel=1`nFromDate=$From`nToDate=$To`nForwardMode=0`nDeposit=10000`nCurrency=USD`nProfitInPips=0`nLeverage=100`nExecutionMode=0`nReport=Tester\GTBPen_$name`nReplaceReport=1`nShutdownTerminal=1`nVisual=0`n[TesterInputs]`n" + (Build $variants[$k] $magic)
    $iniPath = "$r\tester_$name.ini"
    [IO.File]::WriteAllText($iniPath, $ini, [Text.Encoding]::Unicode)
    Get-ChildItem $common -Filter "tester_*.csv" -ErrorAction SilentlyContinue | Clear-Content
    $t0 = Get-Date
    Start-Process $terminal -ArgumentList "/config:`"$iniPath`"" -Wait | Out-Null
    if ((Test-Path "$common\tester_trades.csv") -and (Get-Item "$common\tester_trades.csv").Length -gt 100) {
        Copy-Item "$common\tester_trades.csv" "$r\mt5_$name.csv" -Force
        $n = (Get-Content "$r\mt5_$name.csv" | Measure-Object -Line).Lines - 1
        "{0}: {1:n0}s, trades {2}" -f $name, ((Get-Date) - $t0).TotalSeconds, $n
    } else { "{0}: no/empty export" -f $name }
}
"### run_cc done $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Stop-Transcript | Out-Null
