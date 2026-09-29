#!/bin/bash
# ============================================================================
# REAL-ORDER execution test on the FTMO demo account, isolated from the live setup.
#
# Rebuilds the private rig (/home/mt5/.wine-test + a private portable MT5 install),
# compiles ExecTest.mq5 there and launches it with the account login. ExecTest places,
# reads back, modifies and cancels real orders (market buy/sell + SL, stop pending + SL,
# stop pending + SL + TP, stop move, market close) on XAUUSD and US100.cash and writes
# everything to Common\Files\GoldBreakout\exec_test.log in the RIG prefix.
# The live terminal, its files and its global variables are not touched.
# ============================================================================
set -uo pipefail
SRC=/home/mt5/.wine
TST=/home/mt5/.wine-test
M="$TST/drive_c/Program Files/MetaTrader 5 TEST"
RES=/root/gtb_test_results
LOG="$RES/order_test.log"
D=$(date -u +%Y%m%d)

mkdir -p "$RES"; exec >> "$LOG" 2>&1
echo "############################################################"
echo "### ORDER TEST $(date -u '+%F %T') UTC"
echo "############################################################"
echo "--- live state before (must be identical afterwards)"
md5sum "/home/mt5/.wine/drive_c/Program Files/MetaTrader 5/MQL5/Experts/GoldTrendBreakout/GoldTrendBreakout.ex5" \
       "/home/mt5/.wine/drive_c/Program Files/MetaTrader 5/MQL5/Presets/gtb_live.set" > "$RES/live_before_order.md5"
cat "$RES/live_before_order.md5"
grep -E "time_gmt|balance=|equity=|positions=" "/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/heartbeat.txt"

echo "=== 1/5 removing an old rig"
if [ -e "$TST" ]; then bash /root/rig_cleanup.sh; fi

echo "=== 2/5 copying the prefix + one portable install (live prefix only read)"
cp -a "$SRC" "$TST" || { echo "FATAL"; exit 1; }
cp -a "$SRC/drive_c/Program Files/MetaTrader 5" "$M" || exit 1
chown -R mt5:mt5 "$TST"
rm -f "$M/config/gtb_start.ini"

echo "=== 3/5 start config (login + the test EA on startup)"
LOGIN=""; PASSWORD=""; SERVER=""
. /home/mt5/gtb/account.env
mkdir -p "$M/config" "$M/MQL5/Experts/ExecTest" "$M/MQL5/Presets"
{
  printf '[Common]\r\n'
  printf 'Login=%s\r\nPassword=%s\r\nServer=%s\r\n' "$LOGIN" "$PASSWORD" "$SERVER"
  printf 'KeepPrivate=1\r\nNewsEnable=0\r\n'
  printf '[Experts]\r\nAllowLiveTrading=1\r\nAllowDllImport=0\r\nEnabled=1\r\nAccount=0\r\nProfile=0\r\n'
  printf '[StartUp]\r\nExpert=ExecTest\\ExecTest\r\nSymbol=XAUUSD\r\nPeriod=H1\r\n'
} > "$M/config/rig_order.ini"
chmod 600 "$M/config/rig_order.ini"
install -o mt5 -g mt5 -m 644 /root/ExecTest.mq5 "$M/MQL5/Experts/ExecTest/ExecTest.mq5"

echo "=== 4/5 compiling ExecTest.mq5 in the rig"
sudo -u mt5 -H env DISPLAY=:99 WINEPREFIX="$TST" WINEDEBUG=-all WINEDLLOVERRIDES="mscoree=;mshtml=" \
  bash -c "cd \"$M\" && timeout 240 wine MetaEditor64.exe /portable /compile:'MQL5\\Experts\\ExecTest\\ExecTest.mq5' /log:'MQL5\\Experts\\ExecTest\\compile.log' >/dev/null 2>&1"
iconv -f UTF-16LE -t UTF-8 "$M/MQL5/Experts/ExecTest/compile.log" 2>/dev/null | tr -d '\r' | grep -iE "result|error|warning" | head -20
ls -la "$M/MQL5/Experts/ExecTest/"
[ -f "$M/MQL5/Experts/ExecTest/ExecTest.ex5" ] || { echo "FATAL: no .ex5 - fix the compile errors"; exit 1; }

echo "=== 5/5 running the order test (real orders, 0.01 lots, auto-closed)"
mkdir -p "$TST/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"
cat > /home/mt5/gtb/rig_run_order.sh <<'EOF'
#!/bin/bash
export DISPLAY=:99 WINEPREFIX=/home/mt5/.wine-test WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree=;mshtml="
cd "/home/mt5/.wine-test/drive_c/Program Files/MetaTrader 5 TEST"
exec nice -n 10 wine terminal64.exe /portable '/config:config\rig_order.ini'
EOF
chown mt5:mt5 /home/mt5/gtb/rig_run_order.sh; chmod 750 /home/mt5/gtb/rig_run_order.sh
sudo -u mt5 -H timeout 420 bash /home/mt5/gtb/rig_run_order.sh
echo "    terminal exit=$?"
sleep 5
sudo -u mt5 -H env WINEPREFIX="$TST" wineserver -k 2>/dev/null
sleep 3

C="$TST/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"
cp -f "$C/exec_test.log" "$RES/exec_test.log" 2>/dev/null
echo
echo "================ EXECTEST REPORT ================"
cat "$RES/exec_test.log" 2>/dev/null || echo "(no report file - the EA did not run)"
echo "================ journals ================"
echo "--- Experts journal"
iconv -f UTF-16LE -t UTF-8 "$M/MQL5/logs/$D.log" 2>/dev/null | tr -d '\r' | tail -40
echo "--- terminal journal (order/trade lines)"
iconv -f UTF-16LE -t UTF-8 "$M/logs/$D.log" 2>/dev/null | tr -d '\r' | grep -iE "order|deal|trade|expert|error|invalid" | tail -25
echo
echo "=== the live deployment must be unchanged"
md5sum -c "$RES/live_before_order.md5" 2>&1 || echo "!!! A LIVE FILE CHANGED"
grep -E "time_gmt|balance=|equity=|positions=" "/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/heartbeat.txt"
systemctl is-active gtb-mt5 gtb-mt5-nq gtb-notifier
echo "### ORDER TEST DONE $(date -u '+%F %T') - the rig is still on disk"
