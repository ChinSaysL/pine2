#!/bin/bash
# Validate the afternoon break-even change in the MT5 tester inside the isolated rig, on the SAME
# period twice: InpBeAfterHour=0 (old behaviour) vs =13 (new rule from the research).
set -uo pipefail
SRC=/home/mt5/.wine
TST=/home/mt5/.wine-test
M1="$SRC/drive_c/Program Files/MetaTrader 5 NQ"
T="$TST/drive_c/Program Files/MetaTrader 5 TEST NQ"
RES=/root/gtb_test_results
D=$(date -u +%Y%m%d)
FROM="${RIG_FROM:-2021.09.01}"; TO="${RIG_TO:-2026.09.26}"; MODEL="${RIG_MODEL:-1}"
LOG="$RES/nq_be_validation.log"
mkdir -p "$RES"; exec >> "$LOG" 2>&1

echo
echo "######## NQ afternoon-BE validation $(date -u '+%F %T')   $FROM .. $TO   model=$MODEL ########"
if [ -e "$TST" ]; then echo "removing an old rig"; bash /root/rig_cleanup.sh >/dev/null 2>&1; fi

echo "=== building the rig (private prefix + private NQ install)"
cp -a "$SRC" "$TST" || { echo FATAL; exit 1; }
cp -a "$M1" "$T" || exit 1
chown -R mt5:mt5 "$TST"
rm -f "$T/config/nq_start.ini"

echo "=== installing + compiling the NEW NasdaqORB.mq5 in the rig"
install -d -o mt5 -g mt5 "$T/MQL5/Experts/NasdaqORB"
install -o mt5 -g mt5 -m 644 /root/NasdaqORB.mq5 "$T/MQL5/Experts/NasdaqORB/NasdaqORB.mq5"
rm -f "$T/MQL5/Experts/NasdaqORB/NasdaqORB.ex5"
sudo -u mt5 -H env DISPLAY=:99 WINEPREFIX="$TST" WINEDEBUG=-all WINEDLLOVERRIDES="mscoree;mshtml=;" \
  bash -c "cd '$T' && timeout 240 wine MetaEditor64.exe /portable /compile:'MQL5\\Experts\\NasdaqORB\\NasdaqORB.mq5'" 2>/dev/null
for i in $(seq 1 45); do [ -f "$T/MQL5/Experts/NasdaqORB/NasdaqORB.ex5" ] && break; sleep 2; done
ls -la "$T/MQL5/Experts/NasdaqORB/"
if [ ! -f "$T/MQL5/Experts/NasdaqORB/NasdaqORB.ex5" ]; then
  echo "FATAL: no .ex5 - metaeditor journal:"; tail -c 700 "$T/logs/metaeditor.log" | iconv -f UTF-16LE -t UTF-8; exit 1
fi

echo "=== inputs: baseline = deployed preset with the rule off; new = the shipped preset"
iconv -f UTF-16LE -t UTF-8 "$M1/MQL5/Presets/nq_live.set" 2>/dev/null | tr -d '\r' | grep -E '^[A-Za-z_][A-Za-z0-9_]*=' | grep -v '^InpBe' > "$RES/be_off.txt"
echo "InpBeAfterHour=0" >> "$RES/be_off.txt"
cp -f /root/nq_be.set "$RES/be_on.txt"
echo "    off: $(wc -l < "$RES/be_off.txt") inputs; on: $(wc -l < "$RES/be_on.txt") inputs"
grep -E 'InpBe' "$RES/be_on.txt" | sed 's/^/    /'

LOGIN=""; PASSWORD=""; SERVER=""
. /home/mt5/gtb/account.env
mkini() { # path reportname inputsfile
  { printf '[Common]\nLogin=%s\nPassword=%s\nServer=%s\nKeepPrivate=1\nNewsEnable=0\n' "$LOGIN" "$PASSWORD" "$SERVER"
    printf '[Tester]\nExpert=NasdaqORB\\NasdaqORB.ex5\nSymbol=US100.cash\nPeriod=M15\nOptimization=0\nModel=%s\nFromDate=%s\nToDate=%s\n' "$MODEL" "$FROM" "$TO"
    printf 'ForwardMode=0\nDeposit=10000\nCurrency=USD\nProfitInPips=0\nLeverage=100\nExecutionMode=0\n'
    printf 'Report=%s\nReplaceReport=1\nShutdownTerminal=1\nVisual=0\n' "$2"
    printf '[TesterInputs]\n'; cat "$3"; echo
  } > "$1.utf8"
  iconv -f UTF-8 -t UTF-16LE "$1.utf8" | { printf '\xff\xfe'; cat; } > "$1"
  rm -f "$1.utf8"; chown mt5:mt5 "$1"; echo "    wrote $1"
}
mkdir -p "$T/config"
mkini "$T/config/rig_be_off.ini" NQ_be_off "$RES/be_off.txt"
mkini "$T/config/rig_be_on.ini"  NQ_be_on  "$RES/be_on.txt"

cat > /home/mt5/gtb/rig_be_off.sh <<'EOF'
#!/bin/bash
export DISPLAY=:99 WINEPREFIX=/home/mt5/.wine-test WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree=;mshtml="
cd "/home/mt5/.wine-test/drive_c/Program Files/MetaTrader 5 TEST NQ"
exec nice -n 5 wine terminal64.exe /portable '/config:config\rig_be_off.ini'
EOF
cat > /home/mt5/gtb/rig_be_on.sh <<'EOF'
#!/bin/bash
export DISPLAY=:99 WINEPREFIX=/home/mt5/.wine-test WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree=;mshtml="
cd "/home/mt5/.wine-test/drive_c/Program Files/MetaTrader 5 TEST NQ"
exec nice -n 5 wine terminal64.exe /portable '/config:config\rig_be_on.ini'
EOF
chown mt5:mt5 /home/mt5/gtb/rig_be_off.sh /home/mt5/gtb/rig_be_on.sh
chmod 750 /home/mt5/gtb/rig_be_off.sh /home/mt5/gtb/rig_be_on.sh

CSV="$TST/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/nasdaq_tester_trades.csv"
run_one() { # runner label
  echo; echo "=== TESTER: $2"
  local t0; t0=$(date +%s)
  sudo -u mt5 -H timeout 1800 bash "$1"
  echo "    exit=$? after $(( $(date +%s) - t0 ))s"
  sleep 5
  sudo -u mt5 -H env WINEPREFIX="$TST" wineserver -k >/dev/null 2>&1
  sleep 3
  echo "    tester journal tail:"
  iconv -f UTF-16LE -t UTF-8 "$T/Tester/logs/$D.log" 2>/dev/null | tr -d '\r' | tail -6 | sed 's/^/      /'
  echo "    'afternoon break-even' lines in the tester journal: $(iconv -f UTF-16LE -t UTF-8 "$T/Tester/logs/$D.log" 2>/dev/null | tr -d '\r' | grep -c 'afternoon break-even')"
  if [ -f "$CSV" ]; then cp -f "$CSV" "$RES/nq_be_$2.csv"; echo "    trades: $(( $(wc -l < "$RES/nq_be_$2.csv") - 1 ))  -> $RES/nq_be_$2.csv";
  else echo "    NO TRADE EXPORT"; fi
}
run_one /home/mt5/gtb/rig_be_off.sh off
run_one /home/mt5/gtb/rig_be_on.sh on

summ() {
  awk -F';' 'NR>1 {n++; s+=$9; if($9>0){w+=$9; nn++} else l+=-$9}
             END {if(n) printf "trades %4d   total %+7.2fR   PF %.2f   win %.0f%%\n", n, s, (l>0? w/l:0), 100*nn/n; else print "no trades"}' "$1"
}
echo
echo "=== comparison"
echo "    rule OFF (today's live behaviour): $(summ "$RES/nq_be_off.csv")"
echo "    rule ON  (afternoon break-even):   $(summ "$RES/nq_be_on.csv")"
echo "=== START lines seen by the tester (proves the inputs arrived)"
iconv -f UTF-16LE -t UTF-8 "$T/Tester/logs/$D.log" 2>/dev/null | tr -d '\r' | grep -E "Nasdaq ORB, gate|inputs read" | tail -6
echo "### validation done $(date -u '+%F %T')"
