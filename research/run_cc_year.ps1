param([string]$Windows = "2021,2022,2023,2024,2025,2026", [string]$Pens = "off,p000,p015,p025,p040")
# One-year-window A/B of the minimum-close-penetration rule (InpCloseMinAtr).
# Short windows stay inside the range where the deployed EA trades normally in the tester
# (long runs go silent after ~2.5-4 simulated years - see the write-up), so every run below
# has a verified control. Fixed 1% risk, 50%/50% limits, fresh magic per run.
$r = "C:\Users\Abdo\Downloads\pine2\research"
Start-Transcript -Path "$r\cc_year.log" -Append | Out-Null
"### year A/B started $(Get-Date -Format 'HH:mm:ss')"
$tf = "$env:APPDATA\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075"
$expDir = "$tf\MQL5\Experts\GTBExperiment"
$terminal = Join-Path $env:ProgramFiles "MetaTrader 5\terminal64.exe"
$editor = Join-Path $env:ProgramFiles "MetaTrader 5\MetaEditor64.exe"
$common = Join-Path $env:APPDATA "MetaQuotes\Terminal\Common\Files\GoldBreakout"
New-Item -ItemType Directory -Force -Path $expDir | Out-Null
Copy-Item "$r\ea\GTBClosePen.mq5" "$expDir\GTBClosePen.mq5" -Force
Remove-Item "$expDir\GTBClosePen.ex5" -ErrorAction SilentlyContinue
Start-Process $editor -ArgumentList "/compile:`"$expDir\GTBClosePen.mq5`"", "/log:`"$expDir\compile.log`"" -Wait | Out-Null
for ($i = 0; $i -lt 60 -and -not (Test-Path "$expDir\GTBClosePen.ex5"); $i++) { Start-Sleep -Seconds 1 }
if (Test-Path "$expDir\GTBClosePen.ex5") { "compiled GTBClosePen.ex5: " + (Get-Item "$expDir\GTBClosePen.ex5").Length + " bytes" }
else { "COMPILE FAILED"; Get-Content "$expDir\compile.log" -ErrorAction SilentlyContinue; Stop-Transcript | Out-Null; exit 1 }

function Build([string]$pen, [int]$magic) {
    $lines = @(([IO.File]::ReadAllText("$r\live_inputs.txt") -replace "`r`n", "`n").Split("`n") | Where-Object { $_ -match '=' })
    $extra = @("InpBadMode=1", "InpBadRiskMult=0.5",
               "InpRiskMode=0", "InpRiskPercent=1.0", "InpDailyLimitPct=50", "InpTotalLimitPct=50",
               "InpMagic=$magic")
    $map = @{ "off" = "InpCloseMinAtr=-1"; "p000" = "InpCloseMinAtr=0.0"; "p015" = "InpCloseMinAtr=0.15";
              "p025" = "InpCloseMinAtr=0.25"; "p040" = "InpCloseMinAtr=0.40"; "p060" = "InpCloseMinAtr=0.60";
              "s10" = "InpStopAtr=1.0"; "s125" = "InpStopAtr=1.25"; "s15" = "InpStopAtr=1.5"; "s30" = "InpStopAtr=3.0";
              "t4" = "InpTrailAtr=4.0"; "t5" = "InpTrailAtr=5.0"; "a15" = "InpAddAtR=1.5"; "a0" = "InpAddAtR=0";
              "nobe" = "InpBeAfterAdd=false"; "re15" = "InpReentryEnable=true";
              "re" = "InpReentryEnable=true"; "r10" = "InpReentryStopAtr=1.0"; "r20" = "InpReentryStopAtr=2.0";
              "add2" = "InpAdd2AtR=2.0"; "add25" = "InpAdd2AtR=2.5"; "add3" = "InpAdd2AtR=3.0";
              "frac" = "InpEntryFrac=0.5"; "frac05" = "InpAddAtR=0.5" }
    foreach ($part in $pen.Split("+")) {
        if ($map.ContainsKey($part)) { $extra += $map[$part] } else { $extra += "InpCloseMinAtr=-1" }
    }
    foreach ($pair in $extra) {
        $k = $pair.Split("=")[0]
        $lines = @($lines | Where-Object { $_.Split("=")[0] -ne $k })
        $lines += $pair
    }
    $lines -join "`n"
}
$magicBase = 24241000
$mi = 0
foreach ($y in $Windows.Split(",")) {
    foreach ($p in $Pens.Split(",")) {
        $pen = $p
        $name = "y$y`_$p"
        $magic = $magicBase + $mi; $mi++
        Get-Process terminal64 -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-Sleep -Seconds 1
        $from = "$y.01.01"; $to = "$y.12.31"
        $ini = "[Tester]`nExpert=GTBExperiment\GTBClosePen.ex5`nSymbol=XAUUSD`nPeriod=H1`nOptimization=0`nModel=1`nFromDate=$from`nToDate=$to`nForwardMode=0`nDeposit=10000`nCurrency=USD`nProfitInPips=0`nLeverage=100`nExecutionMode=0`nReport=Tester\Y_$name`nReplaceReport=1`nShutdownTerminal=1`nVisual=0`n[TesterInputs]`n" + (Build $pen $magic)
        $iniPath = "$r\tester_$name.ini"
        [IO.File]::WriteAllText($iniPath, $ini, [Text.Encoding]::Unicode)
        Remove-Item "$common\tester_trades.csv" -ErrorAction SilentlyContinue
        Start-Process $terminal -ArgumentList "/config:`"$iniPath`"" | Out-Null
        for ($i = 0; $i -lt 30 -and -not (Get-Process terminal64 -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Seconds 1 }
        for ($i = 0; $i -lt 200 -and (Get-Process terminal64 -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Seconds 1 }
        Start-Sleep -Seconds 2
        if ((Test-Path "$common\tester_trades.csv") -and (Get-Item "$common\tester_trades.csv").Length -gt 100) {
            Copy-Item "$common\tester_trades.csv" "$r\cc_$name.csv" -Force
            $c = Import-Csv "$r\cc_$name.csv" -Delimiter ';'
            $rsum = ($c | Measure-Object -Property r -Sum).Sum
            "{0}: {1,4} trades  {2,8:n1}R  {3} .. {4}" -f $name, $c.Count, $rsum, $c[0].entry_time_ny, $c[-1].entry_time_ny
        } else { "{0}: NO EXPORT" -f $name }
    }
}
"### year A/B done $(Get-Date -Format 'HH:mm:ss')"
Stop-Transcript | Out-Null
