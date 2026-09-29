#!/bin/bash
# ============================================================================
# REAL-ORDER execution test, run with a free demo session, then restart the live EAs.
#
# Order of operations:
#   1. note the live state, kill any leftover rig terminal
#   2. stop gtb-mt5 (the demo account allows only so many sessions at once)
#   3. run ExecTest in the isolated rig: real orders on XAUUSD + US100.cash
#      (market buy/sell + SL read-back, stop move, market close, BUY/SELL STOP
#       pending + SL, pending + SL + TP, cancel)
#   4. collect the report, close anything left over
#   5. start gtb-mt5 again and restart gtb-mt5-nq, verify both heartbeats
# ============================================================================
set -uo pipefail
TST=/home/mt5/.wine-test
M="$TST/drive_c/Program Files/MetaTrader 5 TEST"
LIVE=/home/mt5/.wine
LF="$LIVE/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"
RES=/root/gtb_test_results
D=$(date -u +%Y%m%d)
exec >> "$RES/order_test.log" 2>&1

echo
echo "######## REAL ORDER TEST (run 3) $(date -u '+%F %T') ########"
echo "--- live state before"
grep -E "time_gmt|balance=|equity=|positions=|halted=" "$LF/heartbeat.txt"

echo "=== 1) killing leftover rig terminals"
pkill -u mt5 -f "MetaTrader 5 TEST" 2>/dev/null
sleep 3
sudo -u mt5 -H env WINEPREFIX="$TST" wineserver -k 2>/dev/null
sleep 2

echo "=== 2) stopping gtb-mt5 to free the demo session"
systemctl stop gtb-mt5
sleep 8
pgrep -u mt5 -af "Program Files/MetaTrader 5\\\\terminal64" | cut -c1-80 || echo "    live terminal stopped"

echo "=== 3) running the order test in the rig"
C="$TST/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"
mkdir -p "$C"; rm -f "$C/exec_test.log"
cat > /home/mt5/gtb/rig_run_order.sh <<'EOF'
#!/bin/bash
export DISPLAY=:99 WINEPREFIX=/home/mt5/.wine-test WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree=;mshtml="
cd "/home/mt5/.wine-test/drive_c/Program Files/MetaTrader 5 TEST"
exec nice -n 10 wine terminal64.exe /portable '/config:config\rig_order.ini'
EOF
chown mt5:mt5 /home/mt5/gtb/rig_run_order.sh; chmod 750 /home/mt5/gtb/rig_run_order.sh
sudo -u mt5 -H env DISPLAY=:99 nohup bash /home/mt5/gtb/rig_run_order.sh >/dev/null 2>&1 &
for i in $(seq 1 90); do
  if grep -q "EXECTEST COMPLETE" "$C/exec_test.log" 2>/dev/null; then echo "    finished after ~$((i*5))s"; break; fi
  sleep 5
done
echo "--- waiting for the terminal to be quiet, then closing it"
sleep 5
pkill -u mt5 -f "MetaTrader 5 TEST" 2>/dev/null
sleep 3
sudo -u mt5 -H env WINEPREFIX="$TST" wineserver -k 2>/dev/null
sleep 3

cp -f "$C/exec_test.log" "$RES/exec_test.log" 2>/dev/null
echo
echo "================ EXECTEST REPORT ================"
cat "$RES/exec_test.log" 2>/dev/null || echo "(no report)"
echo "================ rig journals ================"
echo "--- Experts journal"
iconv -f UTF-16LE -t UTF-8 "$M/MQL5/logs/$D.log" 2>/dev/null | tr -d '\r' | tail -12
echo "--- terminal journal (trade lines)"
iconv -f UTF-16LE -t UTF-8 "$M/logs/$D.log" 2>/dev/null | tr -d '\r' | grep -iE "order|deal|performed|expert|authoriz" | tail -15

echo
echo "=== 4) restarting the live EAs"
systemctl start gtb-mt5
sleep 45
echo "--- gold terminal journal (new lines)"
iconv -f UTF-16LE -t UTF-8 "$LIVE/drive_c/Program Files/MetaTrader 5/logs/$D.log" 2>/dev/null | tr -d '\r' | tail -12
systemctl restart gtb-mt5-nq
sleep 50
echo "--- nasdaq terminal journal (new lines)"
iconv -f UTF-16LE -t UTF-8 "$LIVE/drive_c/Program Files/MetaTrader 5 NQ/logs/$D.log" 2>/dev/null | tr -d '\r' | tail -8

echo
echo "=== 5) final state"
echo "--- gold heartbeat"; cat "$LF/heartbeat.txt"
echo "--- nasdaq heartbeat"; cat "$LF/nasdaq_heartbeat.txt"
echo "--- services"; systemctl is-active gtb-mt5 gtb-mt5-nq gtb-xvfb gtb-vnc gtb-notifier
echo "--- live files unchanged?"; md5sum -c "$RES/live_before_order.md5" 2>&1 || echo "!!! CHANGED"
echo "### DONE $(date -u '+%F %T')"
