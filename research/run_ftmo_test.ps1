param([string]$Name = "ftmo_default", [string]$Inputs = "InpRiskMode=1", [string]$Model = "1", [string]$From = "2025.01.01", [string]$To = "2026.09.26", [string]$Symbol = "XAUUSD")
# Strategy Tester on FTMO's own data: logs the local terminal into the FTMO trial for the run.
$s = "C:\Users\Abdo\AppData\Local\Temp\claude\c--Users-Abdo-Downloads-pine2\477288ce-7536-44c5-bc98-9eeb2dc7aa6e\scratchpad"
$terminal = Join-Path $env:ProgramFiles "MetaTrader 5\terminal64.exe"
$csv = Join-Path $env:APPDATA "MetaQuotes\Terminal\Common\Files\GoldBreakout\tester_trades.csv"
$ini = @"
[Common]
Login=<FTMO login>
Password=<FTMO master password>
Server=FTMO-Demo
[Tester]
Expert=GoldTrendBreakout\GoldTrendBreakout.ex5
Symbol=$Symbol
Period=H1
Optimization=0
Model=$Model
FromDate=$From
ToDate=$To
ForwardMode=0
Deposit=10000
Currency=USD
ProfitInPips=0
Leverage=100
ExecutionMode=0
Report=Tester\GoldBreakout_$Name
ReplaceReport=1
ShutdownTerminal=1
Visual=0
[TesterInputs]
$Inputs
"@
$iniPath = Join-Path $s "tester_$Name.ini"
[IO.File]::WriteAllText($iniPath, $ini, [Text.Encoding]::Unicode)
if (Test-Path $csv) { Clear-Content $csv }
$t0 = Get-Date
$p = Start-Process $terminal -ArgumentList "/config:`"$iniPath`"" -PassThru
$p.WaitForExit(2400000) | Out-Null
Remove-Item $iniPath -ErrorAction SilentlyContinue      # the ini holds the password
"finished in {0:n0}s" -f ((Get-Date) - $t0).TotalSeconds
if ((Test-Path $csv) -and (Get-Item $csv).Length -gt 0) {
    Copy-Item $csv (Join-Path $s "mt5_$Name.csv") -Force
    "trades exported: " + ((Get-Content $csv | Measure-Object -Line).Lines - 1)
} else { "no trade export found" }
