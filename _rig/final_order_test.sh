#!/bin/bash
# ============================================================================
# FINAL real-order test + restart of both live EAs.
#  1. stop gtb-mt5 (the demo account is tight on simultaneous sessions)
#  2. install+compile ExecTest into its OWN folder of the live install
#  3. run it on a temporary config: real orders on XAUUSD + US100.cash
#     (market buy/sell + SL, stop move, close, BUY/SELL STOP + SL, + SL + TP, cancel)
#  4. collect the report, remove the temporary config
#  5. start gtb-mt5 again, restart gtb-mt5-nq, verify both heartbeats
# ============================================================================
set -uo pipefail
LIVE=/home/mt5/.wine
M="$LIVE/drive_c/Program Files/MetaTrader 5"
F="$LIVE/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"
RES=/root/gtb_test_results
D=$(date -u +%Y%m%d)
mkdir -p "$RES"; exec >> "$RES/order_test_final.log" 2>&1

echo
echo "######## FINAL REAL-ORDER TEST $(date -u '+%F %T') ########"
md5sum "$M/MQL5/Experts/GoldTrendBreakout/GoldTrendBreakout.ex5" "$M/MQL5/Presets/gtb_live.set" > "$RES/live_before_final.md5"
echo "--- account before: $(grep -E 'balance=|positions=' "$F/heartbeat.txt" | tr '\n' ' ')"

echo "=== 1) stopping gtb-mt5 for the duration of the test"
systemctl stop gtb-mt5
sleep 8
pkill -u mt5 -f 'MetaTrader 5\\terminal64' 2>/dev/null; sleep 3
sudo -u mt5 -H env WINEPREFIX="$LIVE" wineserver -k 2>/dev/null; sleep 3

echo "=== 2) installing + compiling the test EA (own folder, live EA untouched)"
install -d -o mt5 -g mt5 "$M/MQL5/Experts/ExecTest"
install -o mt5 -g mt5 -m 644 /root/ExecTest.mq5 "$M/MQL5/Experts/ExecTest/ExecTest.mq5"
rm -f "$M/MQL5/Experts/ExecTest/ExecTest.ex5"
sudo -u mt5 -H env DISPLAY=:99 WINEPREFIX="$LIVE" WINEDEBUG=-all WINEDLLOVERRIDES="mscoree=;mshtml=" \
  bash -c "cd '$M' && timeout 240 wine MetaEditor64.exe /portable /compile:'MQL5\\Experts\\ExecTest\\ExecTest.mq5'"
for i in $(seq 1 45); do [ -f "$M/MQL5/Experts/ExecTest/ExecTest.ex5" ] && break; sleep 2; done
ls -la "$M/MQL5/Experts/ExecTest/"
if [ ! -f "$M/MQL5/Experts/ExecTest/ExecTest.ex5" ]; then
  echo "NO EX5 - restarting gtb-mt5"; systemctl start gtb-mt5; exit 1
fi

echo "=== 3) temporary start config + run"
cp -f "$M/config/gtb_start.ini" "$RES/gtb_start.ini.saved" 2>/dev/null
LOGIN=""; PASSWORD=""; SERVER=""
. /home/mt5/gtb/account.env
{
  printf '[Common]\r\n'
  printf 'Login=%s\r\nPassword=%s\r\nServer=%s\r\n' "$LOGIN" "$PASSWORD" "$SERVER"
  printf 'KeepPrivate=1\r\nNewsEnable=0\r\n'
  printf '[Experts]\r\nAllowLiveTrading=1\r\nAllowDllImport=0\r\nEnabled=1\r\nAccount=0\r\nProfile=0\r\n'
  printf '[StartUp]\r\nExpert=ExecTest\\ExecTest\r\nSymbol=XAUUSD\r\nPeriod=H1\r\n'
} > "$M/config/exec_test.ini"
chmod 600 "$M/config/exec_test.ini"; chown mt5:mt5 "$M/config/exec_test.ini"

cat > /home/mt5/gtb/run_exec_test.sh <<'EOF'
#!/bin/bash
export DISPLAY=:99 WINEPREFIX=/home/mt5/.wine WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree=;mshtml="
cd "/home/mt5/.wine/drive_c/Program Files/MetaTrader 5"
exec nice -n 5 wine terminal64.exe /portable '/config:config\exec_test.ini'
EOF
chown mt5:mt5 /home/mt5/gtb/run_exec_test.sh; chmod 750 /home/mt5/gtb/run_exec_test.sh

rm -f "$F/exec_test.log"
sudo -u mt5 -H env DISPLAY=:99 nohup bash /home/mt5/gtb/run_exec_test.sh >/dev/null 2>&1 &
for i in $(seq 1 90); do
  if grep -q "EXECTEST COMPLETE" "$F/exec_test.log" 2>/dev/null; then echo "    completed after ~$((i*5))s"; break; fi
  sleep 5
done
sleep 3
pkill -u mt5 -f 'MetaTrader 5\\terminal64' 2>/dev/null
sleep 4
sudo -u mt5 -H env WINEPREFIX="$LIVE" wineserver -k 2>/dev/null
sleep 3
cp -f "$F/exec_test.log" "$RES/live_exec_test.log" 2>/dev/null

echo
echo "================ EXECTEST REPORT ================"
cat "$RES/live_exec_test.log" 2>/dev/null || echo "(no report)"
echo "================ EA journal (tail) ================"
iconv -f UTF-16LE -t UTF-8 "$M/MQL5/logs/$D.log" 2>/dev/null | tr -d '\r' | tail -10

echo
echo "=== 4) cleanup + restart the live EAs"
rm -f "$M/config/exec_test.ini"
systemctl start gtb-mt5
sleep 50
echo "--- gold journal (after restart)"; iconv -f UTF-16LE -t UTF-8 "$M/logs/$D.log" | tr -d '\r' | tail -6
systemctl restart gtb-mt5-nq
sleep 55

echo
echo "=== 5) final state"
echo "--- gold heartbeat"; cat "$F/heartbeat.txt"
echo "--- nasdaq heartbeat"; cat "$F/nasdaq_heartbeat.txt"
echo "--- services"; systemctl is-active gtb-mt5 gtb-mt5-nq gtb-xvfb gtb-vnc gtb-notifier
echo "--- live files unchanged?"; md5sum -c "$RES/live_before_final.md5" 2>&1 || echo "!!! CHANGED"
echo "### FINAL DONE $(date -u '+%F %T')"
