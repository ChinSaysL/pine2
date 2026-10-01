#!/bin/bash
# Corrected single-day check (tester window 2026.09.28..2026.10.03, which includes the 00:16 UTC bar
# on 2026-10-01): does each variant still take the trade whose NEW YORK entry time is 2026.09.30 20:16?
# The gold EA's tester export writes New York times, so that is the row we look for.
set -uo pipefail
TST=/home/mt5/.wine-test
T="$TST/drive_c/Program Files/MetaTrader 5 TEST"
RES=/root/gtb_test_results
LOG="$RES/gold_filters.log"
exec >> "$LOG" 2>&1

LOGIN=""; PASSWORD=""; SERVER=""
. /home/mt5/gtb/account.env
mkini() { # path reportname inputfile
  { printf '[Common]\nLogin=%s\nPassword=%s\nServer=%s\nKeepPrivate=1\nNewsEnable=0\n' "$LOGIN" "$PASSWORD" "$SERVER"
    printf '[Tester]\nExpert=GoldTrendBreakout\\GoldTrendBreakout.ex5\nSymbol=XAUUSD\nPeriod=H1\nOptimization=0\nModel=1\nFromDate=2026.09.28\nToDate=2026.10.03\n'
    printf 'ForwardMode=0\nDeposit=10000\nCurrency=USD\nProfitInPips=0\nLeverage=100\nExecutionMode=0\n'
    printf 'Report=%s\nReplaceReport=1\nShutdownTerminal=1\nVisual=0\n' "$2"
    printf '[TesterInputs]\n'; cat "$3"; echo
  } > "$1.utf8"
  iconv -f UTF-8 -t UTF-16LE "$1.utf8" | { printf '\xff\xfe'; cat; } > "$1"
  rm -f "$1.utf8"; chown mt5:mt5 "$1"
}
mkdir -p "$T/config"
CSV="$TST/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/tester_trades.csv"

echo
echo "=========== PHASE C (day window 2026.09.28..2026.10.03) $(date -u '+%F %T') ==========="
for v in base buf15 buf30 buf60 nyonly adx20 ema10 chan12; do
  f="$RES/in_$v.txt"
  cp -f "$RES/gold_live_inputs.txt" "$f"
  case "$v" in
    buf15)  echo "InpBufAtr=0.15" >> "$f";;
    buf30)  echo "InpBufAtr=0.30" >> "$f";;
    buf60)  echo "InpBufAtr=0.60" >> "$f";;
    nyonly) echo "InpBadMode=0"   >> "$f";;
    adx20)  echo "InpAdxMin=20"   >> "$f";;
    ema10)  echo "InpEmaSepPct=1.0" >> "$f";;
    chan12) echo "InpChanHours=12" >> "$f";;
  esac
  mkini "$T/config/gtc_$v.ini" "GTC_$v" "$f"
  cat > /home/mt5/gtb/gtc_run.sh <<EOF
#!/bin/bash
export DISPLAY=:99 WINEPREFIX=$TST WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree=;mshtml="
cd "$T"
exec nice -n 5 wine terminal64.exe /portable '/config:config\\gtc_$v.ini'
EOF
  chown mt5:mt5 /home/mt5/gtb/gtc_run.sh; chmod 750 /home/mt5/gtb/gtc_run.sh
  rm -f "$CSV"
  sudo -u mt5 -H timeout 900 bash /home/mt5/gtb/gtc_run.sh >/dev/null 2>&1
  sleep 4
  sudo -u mt5 -H env WINEPREFIX="$TST" wineserver -k >/dev/null 2>&1
  sleep 2
  echo "  --- $v"
  if [ -f "$CSV" ]; then
    cp -f "$CSV" "$RES/gold_C_$v.csv"
    echo "      trades in window: $(( $(wc -l < "$CSV") - 1 ))"
    grep -a '^2026.09.30 2' "$CSV" | sed 's/^/      /' || true
  else
    echo "      no trades at all in the window"
  fi
done
echo "### phase C done $(date -u '+%F %T')"
