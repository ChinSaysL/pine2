# 4-year FTMO-data runs of the regime-filter variants (fixed 1%, guards off). Every input is written
# exactly once (MT5 keeps the first value of a duplicated key and remembers unlisted ones between runs).
param([string]$Symbol = "XAUUSD", [string]$Prefix = "v")
$s = "C:\Users\Abdo\AppData\Local\Temp\claude\c--Users-Abdo-Downloads-pine2\477288ce-7536-44c5-bc98-9eeb2dc7aa6e\scratchpad"
function Build([hashtable]$over) {
    $lines = ([IO.File]::ReadAllText("$s\live_inputs.txt") -replace "`r`n", "`n").Split("`n") | Where-Object { $_ -match '=' }
    $all = @{ "InpRiskMode" = "0"; "InpPropRules" = "false" } + $over
    ($lines | ForEach-Object { $k = $_.Split("=")[0]; if ($all.ContainsKey($k)) { "$k=$($all[$k])" } else { $_ } }) -join "`n"
}
$variants = [ordered]@{
    "regoff" = @{ "InpRegimeFilter" = "false" };
    "regon"  = @{ "InpRegimeFilter" = "true" };
}
foreach ($k in $variants.Keys) {
    $name = "${Prefix}_$k"
    $out = powershell -ExecutionPolicy Bypass -File "$s\run_ftmo_test.ps1" -Name $name -Inputs (Build $variants[$k]) -From 2022.09.26 -To 2026.09.26 -Symbol $Symbol
    Copy-Item (Join-Path $env:APPDATA "MetaQuotes\Terminal\Common\Files\GoldBreakout\tester_paper.csv") "$s\paper_$name.csv" -Force
    "$name : $($out -join ' | ')"
}
