#!/bin/bash
# Gold Trend Breakout bot - step 9: EXECUTION TEST of the deployed EAs, isolated from the live setup.
#
# Runs the MetaTrader 5 Strategy Tester with the DEPLOYED experts (.ex5) and the DEPLOYED presets
# (gtb_live.set / nq_live.set) on FTMO's own symbol data and reports whether the EAs really place,
# modify and close orders. Nothing under /home/mt5/.wine is written: the test runs in a private
# copy of the Wine prefix, so the live terminal, its Common\Files (events.log, heartbeat.txt,
# halt.flag, tester_*.csv), its MQL5 data folder and its terminal global variables stay untouched
# (verified with md5 before/after).
#
# Usage:  bash 09_test_ea_execution.sh [from] [to] [model]
#         bash 09_test_ea_execution.sh 2026.08.01 2026.09.26 1
#         bash 09_test_ea_execution.sh --cleanup          # drop an old rig first
#
# The MT5 tester refuses to run without an account selected ("tester not started because the
# account is not specified"), so the rig terminal logs into the same FTMO demo account for the
# duration of the run. Measured: this does not disturb the live EA's session.
# Results: /root/gtb_test_results (one tester CSV per EA + the full log).
set -uo pipefail

SRC_PREFIX=/home/mt5/.wine
TST_PREFIX=/home/mt5/.wine-test
SRC_MT5="$SRC_PREFIX/drive_c/Program Files/MetaTrader 5"
SRC_NQ="$SRC_PREFIX/drive_c/Program Files/MetaTrader 5 NQ"
TST_MT5="$TST_PREFIX/drive_c/Program Files/MetaTrader 5 TEST"
TST_NQ="$TST_PREFIX/drive_c/Program Files/MetaTrader 5 TEST NQ"
RES=/root/gtb_test_results
CLEAN=""
if [ "${1:-}" = "--cleanup" ]; then CLEAN=1; shift; fi
FROM="${1:-${RIG_FROM:-2026.05.01}}"
TO="${2:-${RIG_TO:-2026.09.26}}"
MODEL="${3:-${RIG_MODEL:-1}}"    # 1 = 1 minute OHLC (fast), 4 = every tick based on real ticks
LOG="$RES/execution_test.log"
D=$(date -u +%Y%m%d)
COMMON="$TST_PREFIX/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"

mkdir -p "$RES"
exec >> "$LOG" 2>&1
echo "############################################################"
echo "### EXECUTION TEST $(date -u '+%F %T')  $FROM..$TO  model=$MODEL"
echo "############################################################"

if [ -n "$CLEAN" ] || [ -e "$TST_PREFIX" ]; then
  echo "=== removing an existing rig"
  bash /root/rig_cleanup.sh || true
fi

echo "=== 1/6 snapshot of the live deployment (verified again at the end)"
md5sum "$SRC_MT5/MQL5/Experts/GoldTrendBreakout/GoldTrendBreakout.mq5" \
       "$SRC_MT5/MQL5/Experts/GoldTrendBreakout/GoldTrendBreakout.ex5" \
       "$SRC_MT5/MQL5/Presets/gtb_live.set" \
       "$SRC_NQ/MQL5/Presets/nq_live.set" \
       "$SRC_NQ/MQL5/Experts/NasdaqORB/NasdaqORB.ex5" > "$RES/live_before.md5"
cat "$RES/live_before.md5"
grep -E "time_gmt|connected|positions=" "$SRC_PREFIX/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/heartbeat.txt"

echo "=== 2/6 building the isolated rig (private Wine prefix + private portable MT5 installs)"
cp -a "$SRC_PREFIX" "$TST_PREFIX" || { echo "FATAL: prefix copy failed"; exit 1; }
cp -a "$SRC_MT5" "$TST_MT5" || exit 1
cp -a "$SRC_NQ"  "$TST_NQ"  || exit 1
chown -R mt5:mt5 "$TST_PREFIX"
rm -f "$TST_MT5/config/gtb_start.ini" "$TST_NQ/config/nq_start.ini"   # never auto-start the live EAs

echo "=== 3/6 tester .ini files built from the DEPLOYED presets"
iconv -f UTF-16LE -t UTF-8 "$SRC_MT5/MQL5/Presets/gtb_live.set" 2>/dev/null | tr -d '\r' | grep -E '^[A-Za-z_][A-Za-z0-9_]*=' > "$RES/gold_inputs.txt"
iconv -f UTF-16LE -t UTF-8 "$SRC_NQ/MQL5/Presets/nq_live.set"   2>/dev/null | tr -d '\r' | grep -E '^[A-Za-z_][A-Za-z0-9_]*=' > "$RES/nq_inputs.txt"
echo "    gold inputs $(wc -l < "$RES/gold_inputs.txt"), nq inputs $(wc -l < "$RES/nq_inputs.txt")"

LOGIN=""; PASSWORD=""; SERVER=""
. /home/mt5/gtb/account.env


mkini() { # path expert symbol period report inputsfile
  { printf '[Common]\nLogin=%s\nPassword=%s\nServer=%s\nKeepPrivate=1\nNewsEnable=0\n' "$LOGIN" "$PASSWORD" "$SERVER"
    printf '[Tester]\nExpert=%s\nSymbol=%s\nPeriod=%s\nOptimization=0\nModel=%s\nFromDate=%s\nToDate=%s\n' \
           "$2" "$3" "$4" "$MODEL" "$FROM" "$TO"
    printf 'ForwardMode=0\nDeposit=10000\nCurrency=USD\nProfitInPips=0\nLeverage=100\nExecutionMode=0\n'
    printf 'Report=%s\nReplaceReport=1\nShutdownTerminal=1\nVisual=0\n' "$5"
    printf '[TesterInputs]\n'; cat "$6"; echo
  } > "$1.utf8"
  iconv -f UTF-8 -t UTF-16LE "$1.utf8" | { printf '\xff\xfe'; cat; } > "$1"    # MT5 wants UTF-16
  rm -f "$1.utf8"; chown mt5:mt5 "$1"; echo "    wrote $1"
}
mkdir -p "$TST_MT5/config" "$TST_NQ/config" "$COMMON"
mkini "$TST_MT5/config/rig_gold.ini" 'GoldTrendBreakout\GoldTrendBreakout.ex5' XAUUSD H1 GoldBreakout_rig "$RES/gold_inputs.txt"
mkini "$TST_NQ/config/rig_nq.ini"    'NasdaqORB\NasdaqORB.ex5'                'US100.cash' M15 NasdaqORB_rig "$RES/nq_inputs.txt"

echo "=== 4/6 runners"
cat > /home/mt5/gtb/rig_run_gold.sh <<'EOF'
#!/bin/bash
export DISPLAY=:99 WINEPREFIX=/home/mt5/.wine-test WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree=;mshtml="
cd "/home/mt5/.wine-test/drive_c/Program Files/MetaTrader 5 TEST"
exec nice -n 10 wine terminal64.exe /portable '/config:config\rig_gold.ini'
EOF
cat > /home/mt5/gtb/rig_run_nq.sh <<'EOF'
#!/bin/bash
export DISPLAY=:99 WINEPREFIX=/home/mt5/.wine-test WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree=;mshtml="
cd "/home/mt5/.wine-test/drive_c/Program Files/MetaTrader 5 TEST NQ"
exec nice -n 10 wine terminal64.exe /portable '/config:config\rig_nq.ini'
EOF
chown mt5:mt5 /home/mt5/gtb/rig_run_gold.sh /home/mt5/gtb/rig_run_nq.sh
chmod 750 /home/mt5/gtb/rig_run_gold.sh /home/mt5/gtb/rig_run_nq.sh


run_one() { # label install-dir runner export-file
  echo; echo "=== 5/6 TESTER: $1"
  local t0; t0=$(date +%s)
  sudo -u mt5 -H timeout 1800 bash "$3"
  echo "    exit=$? after $(( $(date +%s) - t0 ))s"
  sleep 5
  sudo -u mt5 -H env WINEPREFIX="$TST_PREFIX" wineserver -k 2>/dev/null; sleep 3
  echo "    $1 terminal journal:"
  iconv -f UTF-16LE -t UTF-8 "$2/logs/$D.log" 2>/dev/null | tr -d '\r' | tail -10 | sed 's/^/      /'
  echo "    $1 tester journal:"
  iconv -f UTF-16LE -t UTF-8 "$2/Tester/logs/$D.log" 2>/dev/null | tr -d '\r' | tail -6 | sed 's/^/      /'
  local errs=0 f
  for f in "$2"/Tester/logs/$D.log "$2"/Tester/Agent-*/logs/$D.log; do
    [ -f "$f" ] || continue
    errs=$(( errs + $(iconv -f UTF-16LE -t UTF-8 "$f" 2>/dev/null | tr -d '\r' | \
      grep -icE '\[(invalid|failed|rejected|requote|error|no money|off quotes)\]|not enough money|unsupported filling|invalid stops|invalid volume|market closed|trade disabled') ))
  done
  echo "    $1 order errors (must be 0): $errs"
  if [ -f "$COMMON/$4" ]; then
    cp -f "$COMMON/$4" "$RES/$4"
    echo "    $1 trades: $(( $(wc -l < "$RES/$4") - 1 ))  ->  $RES/$4"
    head -5 "$RES/$4" | sed 's/^/      /'
  else
    echo "    !!! NO TRADE EXPORT ($COMMON/$4)"
  fi
}

run_one GOLD "$TST_MT5" /home/mt5/gtb/rig_run_gold.sh tester_trades.csv
cp -f "$COMMON/tester_paper.csv" "$RES/gold_tester_paper.csv" 2>/dev/null
run_one NQ "$TST_NQ" /home/mt5/gtb/rig_run_nq.sh nasdaq_tester_trades.csv

echo
echo "=== 6/6 the live deployment must be unchanged"
md5sum -c "$RES/live_before.md5" 2>&1 || echo "!!! A LIVE FILE CHANGED - investigate before going live"
grep -E "time_gmt|connected|positions=|regime=" "$SRC_PREFIX/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/heartbeat.txt"
systemctl is-active gtb-mt5 gtb-mt5-nq gtb-xvfb gtb-vnc gtb-notifier
echo "The rig stays on disk (~3.5 GB): remove it with 'bash /root/rig_cleanup.sh'"
echo "### EXECUTION TEST DONE $(date -u '+%F %T') - full log: $LOG"
