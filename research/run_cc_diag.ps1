param([string]$From = "2020.01.01", [string]$To = "2026.10.01")
# Gold EA tester runner with proper waiting + coverage verification.
#   research profile: fixed 1% risk, limits 50%/50% (the EA's 2.5%/5% guards stop trading for good once
#   the total limit is touched, which truncates any backtest that starts at the initial balance),
#   fresh magic per run so no stale 'limitStop' global variable is inherited.
#   After each run: wait for the terminal to really exit, then report rows + first/last trade date.
$r = "C:\Users\Abdo\Downloads\pine2\research"
Start-Transcript -Path "$r\cc_diag.log" -Append | Out-Null
"### runner started $(Get-Date -Format 'HH:mm:ss') window $From .. $To"
$tf = "$env:APPDATA\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075"
$expDir = "$tf\MQL5\Experts\GTBExperiment"
$terminal = Join-Path $env:ProgramFiles "MetaTrader 5\terminal64.exe"
$editor = Join-Path $env:ProgramFiles "MetaTrader 5\MetaEditor64.exe"
$common = Join-Path $env:APPDATA "MetaQuotes\Terminal\Common\Files\GoldBreakout"

New-Item -ItemType Directory -Force -Path $expDir | Out-Null
Copy-Item "$r\ea\GTBClosePen.mq5" "$expDir\GTBClosePen.mq5" -Force
if (-not (Test-Path "$expDir\GTBClosePen.ex5")) {
    Start-Process $editor -ArgumentList "/compile:`"$expDir\GTBClosePen.mq5`"", "/log:`"$expDir\compile.log`"" -Wait | Out-Null
}

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

function RunOne([string]$name, [string]$from, [string]$to, [string]$pen, [int]$magic) {
    Get-Process terminal64 -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
    $ini = "[Tester]`nExpert=GTBExperiment\GTBClosePen.ex5`nSymbol=XAUUSD`nPeriod=H1`nOptimization=0`nModel=1`nFromDate=$from`nToDate=$to`nForwardMode=0`nDeposit=10000`nCurrency=USD`nProfitInPips=0`nLeverage=100`nExecutionMode=0`nReport=Tester\CC_$name`nReplaceReport=1`nShutdownTerminal=1`nVisual=0`n[TesterInputs]`n" + (Build $pen $magic)
    $iniPath = "$r\tester_$name.ini"
    [IO.File]::WriteAllText($iniPath, $ini, [Text.Encoding]::Unicode)
    Remove-Item "$common\tester_trades.csv" -ErrorAction SilentlyContinue
    $t0 = Get-Date
    Start-Process $terminal -ArgumentList "/config:`"$iniPath`"" | Out-Null
    # wait for the terminal to appear, then to disappear again (the tester shuts it down)
    for ($i = 0; $i -lt 30 -and -not (Get-Process terminal64 -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Seconds 2 }
    for ($i = 0; $i -lt 300 -and (Get-Process terminal64 -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 3
    $secs = ((Get-Date) - $t0).TotalSeconds
    if ((Test-Path "$common\tester_trades.csv") -and (Get-Item "$common\tester_trades.csv").Length -gt 100) {
        Copy-Item "$common\tester_trades.csv" "$r\cc_$name.csv" -Force
        $c = Import-Csv "$r\cc_$name.csv" -Delimiter ';'
        $yrs = ($c | Group-Object { $_.entry_time_ny.Substring(0, 4) } | ForEach-Object { $_.Name + ':' + $_.Count }) -join ' '
        "{0} [{1}..{2}] {3:n0}s  {4} trades  {5} .. {6}`n      {7}" -f $name, $from, $to, $secs, $c.Count, $c[0].entry_time_ny, $c[-1].entry_time_ny, $yrs
    } else { "{0} [{1}..{2}] {3:n0}s  NO EXPORT" -f $name, $from, $to, $secs }
}

"=== control (rule off) over three windows"
RunOne "ctrl2020" $From $To "-1" 24240300
RunOne "ctrlFull" "2010.06.01" "2026.10.01" "-1" 24240301
"### runner done $(Get-Date -Format 'HH:mm:ss')"
Stop-Transcript | Out-Null
