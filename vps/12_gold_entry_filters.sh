#!/bin/bash
# Would any entry filter have avoided the 2026-10-01 00:16 UTC gold trade (the sweep of the 24h low)?
# Phase A: replay 2026-09-29..2026-10-01 per variant (fast) - does the trade still happen?
# Phase B: the same variants over 2021-09-01..2026-10-01 - what does the filter cost the strategy?
set -uo pipefail
SRC=/home/mt5/.wine
TST=/home/mt5/.wine-test
M1="$SRC/drive_c/Program Files/MetaTrader 5"
T="$TST/drive_c/Program Files/MetaTrader 5 TEST"
RES=/root/gtb_test_results
LOG="$RES/gold_filters.log"
mkdir -p "$RES"; exec >> "$LOG" 2>&1

echo
echo "######## GOLD entry-filter experiment $(date -u '+%F %T') ########"
if [ -e "$TST" ]; then bash /root/rig_cleanup.sh >/dev/null 2>&1; fi
echo "=== building the rig"
cp -a "$SRC" "$TST" || { echo FATAL; exit 1; }
cp -a "$M1" "$T" || exit 1
chown -R mt5:mt5 "$TST"
rm -f "$T/config/gtb_start.ini"
echo "=== installing + compiling the live gold EA in the rig"
install -d -o mt5 -g mt5 "$T/MQL5/Experts/GoldTrendBreakout"
install -o mt5 -g mt5 -m 644 "$M1/MQL5/Experts/GoldTrendBreakout/GoldTrendBreakout.mq5" "$T/MQL5/Experts/GoldTrendBreakout/"
rm -f "$T/MQL5/Experts/GoldTrendBreakout/GoldTrendBreakout.ex5"
sudo -u mt5 -H env DISPLAY=:99 WINEPREFIX="$TST" WINEDEBUG=-all WINEDLLOVERRIDES="mscoree=;mshtml=" \
  bash -c "cd '$T' && timeout 240 wine MetaEditor64.exe /portable /compile:'MQL5\\Experts\\GoldTrendBreakout\\GoldTrendBreakout.mq5'" 2>/dev/null
for i in $(seq 1 45); do [ -f "$T/MQL5/Experts/GoldTrendBreakout/GoldTrendBreakout.ex5" ] && break; sleep 2; done
[ -f "$T/MQL5/Experts/GoldTrendBreakout/GoldTrendBreakout.ex5" ] || { echo "FATAL: no .ex5"; exit 1; }

iconv -f UTF-16LE -t UTF-8 "$M1/MQL5/Presets/gtb_live.set" 2>/dev/null | tr -d '\r' | grep -E '^[A-Za-z_][A-Za-z0-9_]*=' > "$RES/gold_live_inputs.txt"
echo "    live preset inputs: $(wc -l < "$RES/gold_live_inputs.txt")"

variants() {
  echo "base|"
  echo "buf15|InpBufAtr=0.15"
  echo "buf30|InpBufAtr=0.30"
  echo "buf60|InpBufAtr=0.60"
  echo "nyonly|InpBadMode=0"
  echo "adx20|InpAdxMin=20"
  echo "ema10|InpEmaSepPct=1.0"
  echo "chan12|InpChanHours=12"
}

LOGIN=""; PASSWORD=""; SERVER=""
. /home/mt5/gtb/account.env
mkini() { # path reportname inputfile from to
  { printf '[Common]\nLogin=%s\nPassword=%s\nServer=%s\nKeepPrivate=1\nNewsEnable=0\n' "$LOGIN" "$PASSWORD" "$SERVER"
    printf '[Tester]\nExpert=GoldTrendBreakout\\GoldTrendBreakout.ex5\nSymbol=XAUUSD\nPeriod=H1\nOptimization=0\nModel=1\nFromDate=%s\nToDate=%s\n' "$4" "$5"
    printf 'ForwardMode=0\nDeposit=10000\nCurrency=USD\nProfitInPips=0\nLeverage=100\nExecutionMode=0\n'
    printf 'Report=%s\nReplaceReport=1\nShutdownTerminal=1\nVisual=0\n' "$2"
    printf '[TesterInputs]\n'; cat "$3"; echo
  } > "$1.utf8"
  iconv -f UTF-8 -t UTF-16LE "$1.utf8" | { printf '\xff\xfe'; cat; } > "$1"
  rm -f "$1.utf8"; chown mt5:mt5 "$1"
}
mkdir -p "$T/config"
CSV="$TST/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/tester_trades.csv"

run_variant() { # name from to phase
  local name="$1" from="$2" to="$3" phase="$4"
  local f="$RES/in_$name.txt"
  cp -f "$RES/gold_live_inputs.txt" "$f"
  variants | awk -F'|' -v n="$name" '$1==n {print $2}' >> "$f"
  mkini "$T/config/gtf_$name.ini" "GTF_$name" "$f" "$from" "$to"
  cat > /home/mt5/gtb/gtf_run.sh <<EOF
#!/bin/bash
export DISPLAY=:99 WINEPREFIX=$TST WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree=;mshtml="
cd "$T"
exec nice -n 5 wine terminal64.exe /portable '/config:config\\gtf_$name.ini'
EOF
  chown mt5:mt5 /home/mt5/gtb/gtf_run.sh; chmod 750 /home/mt5/gtb/gtf_run.sh
  rm -f "$CSV"
  sudo -u mt5 -H timeout 2400 bash /home/mt5/gtb/gtf_run.sh >/dev/null 2>&1
  sleep 4
  sudo -u mt5 -H env WINEPREFIX="$TST" wineserver -k >/dev/null 2>&1
  sleep 2
  [ -f "$CSV" ] && cp -f "$CSV" "$RES/gold_${phase}_$name.csv"
}

echo
echo "=========== PHASE A: 2026-09-29..2026-10-01 - is the 00:16 trade still taken? ==========="
for v in $(variants | cut -d'|' -f1); do
  run_variant "$v" "2026.09.29" "2026.10.01" "A"
  f="$RES/gold_A_$v.csv"
  if [ -f "$f" ]; then
    echo "  $v: $(grep -c '^2026.10.01' "$f") trade(s) on 2026-10-01   $(grep '^2026.10.01' "$f" | cut -d';' -f1,3,4,5,9 | tr '\n' ' ')"
  else
    echo "  $v: no trades in the window"
  fi
done

echo
echo "=========== PHASE B: 2021-09-01..2026-10-01 ==========="
for v in $(variants | cut -d'|' -f1); do
  run_variant "$v" "2021.09.01" "2026.10.01" "B"
  f="$RES/gold_B_$v.csv"
  if [ -f "$f" ]; then
    printf '  %-7s ' "$v"
    awk -F';' 'NR>1 {n++; s+=$9; if($9>0){w+=$9; nn++} else l+=-$9} END {printf "trades %4d  total %+7.1fR  PF %.2f  win %.0f%%", n, s, (l>0?w/l:0), 100*nn/n}' "$f"
    echo "   today: $(grep -c '^2026.10.01' "$f")"
  else
    echo "  $v: NO EXPORT"
  fi
done
echo "### gold filter experiment done $(date -u '+%F %T')"
