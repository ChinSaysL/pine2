# Real-EA comparison of bad-regime modes on MetaQuotes gold data, live risk settings. Every input written once.
param([string]$From = "2010.06.01", [string]$To = "2026.09.26")
$r = "C:\Users\Abdo\Downloads\pine2\research"
$terminal = Join-Path $env:ProgramFiles "MetaTrader 5\terminal64.exe"
$common = Join-Path $env:APPDATA "MetaQuotes\Terminal\Common\Files\GoldBreakout"
function Build([hashtable]$over) {
    $lines = ([IO.File]::ReadAllText("$r\live_inputs.txt") -replace "`r`n", "`n").Split("`n") | Where-Object { $_ -match '=' }
    $lines += "InpBadMode=1"; $lines += "InpBadRiskMult=0.5"
    ($lines | ForEach-Object { $k = $_.Split("=")[0]; if ($over.ContainsKey($k)) { "$k=$($over[$k])" } else { $_ } }) -join "`n"
}
$variants = [ordered]@{ "nyonly" = @{ "InpBadMode" = "0" }; "halfrisk" = @{ "InpBadMode" = "1" }; "nofilter" = @{ "InpRegimeFilter" = "false" } }
foreach ($k in $variants.Keys) {
    $name = "bm_$k"
    $ini = "[Tester]`nExpert=GoldTrendBreakout\GoldTrendBreakout.ex5`nSymbol=XAUUSD`nPeriod=H1`nOptimization=0`nModel=1`nFromDate=$From`nToDate=$To`nForwardMode=0`nDeposit=10000`nCurrency=USD`nProfitInPips=0`nLeverage=100`nExecutionMode=0`nReport=Tester\GoldBreakout_$name`nReplaceReport=1`nShutdownTerminal=1`nVisual=0`n[TesterInputs]`n" + (Build $variants[$k])
    $iniPath = "$r\tester_$name.ini"
    [IO.File]::WriteAllText($iniPath, $ini, [Text.Encoding]::Unicode)
    Get-ChildItem $common -Filter "tester_*.csv" -ErrorAction SilentlyContinue | Clear-Content
    $t0 = Get-Date
    $p = Start-Process $terminal -ArgumentList "/config:`"$iniPath`"" -PassThru
    $p.WaitForExit(3600000) | Out-Null
    Copy-Item "$common\tester_trades.csv" "$r\mt5_$name.csv" -Force
    Copy-Item "$common\tester_paper.csv" "$r\paper_$name.csv" -Force
    "{0}: {1:n0}s, trades {2}" -f $name, ((Get-Date) - $t0).TotalSeconds, ((Get-Content "$r\mt5_$name.csv" | Measure-Object -Line).Lines - 1)
}