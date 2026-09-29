#!/bin/bash
# Run the real-order test in the rig that already exists (permissions fixed, compile with a wait).
set -uo pipefail
TST=/home/mt5/.wine-test
M="$TST/drive_c/Program Files/MetaTrader 5 TEST"
RES=/root/gtb_test_results
D=$(date -u +%Y%m%d)
exec >> "$RES/order_test.log" 2>&1
echo
echo "######## ORDER TEST (run 2) $(date -u '+%F %T') ########"

echo "=== fixing the EA folder ownership (root-owned folders make MetaEditor fail silently)"
install -d -o mt5 -g mt5 "$M/MQL5/Experts/ExecTest"
install -o mt5 -g mt5 -m 644 /root/ExecTest.mq5 "$M/MQL5/Experts/ExecTest/ExecTest.mq5"
ls -la "$M/MQL5/Experts/ExecTest/"

echo "=== compiling (waiting for ExecTest.ex5 to appear)"
rm -f "$M/MQL5/Experts/ExecTest/ExecTest.ex5"
sudo -u mt5 -H env DISPLAY=:99 WINEPREFIX="$TST" WINEDEBUG=-all WINEDLLOVERRIDES="mscoree=;mshtml=" \
  bash -c "cd '$M' && timeout 240 wine MetaEditor64.exe /portable /compile:'MQL5\\Experts\\ExecTest\\ExecTest.mq5'"
for i in $(seq 1 45); do [ -f "$M/MQL5/Experts/ExecTest/ExecTest.ex5" ] && break; sleep 2; done
ls -la "$M/MQL5/Experts/ExecTest/"
if [ ! -f "$M/MQL5/Experts/ExecTest/ExecTest.ex5" ]; then
  echo "STILL NO EX5 - metaeditor journal:"
  tail -c 600 "$M/logs/metaeditor.log" | iconv -f UTF-16LE -t UTF-8
  exit 1
fi

echo "=== running the order test: REAL orders on the demo, 0.01 lots, auto-closed"
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
sudo -u mt5 -H timeout 420 bash /home/mt5/gtb/rig_run_order.sh
echo "    terminal exit=$?"
sleep 5
sudo -u mt5 -H env WINEPREFIX="$TST" wineserver -k 2>/dev/null
sleep 3

cp -f "$C/exec_test.log" "$RES/exec_test.log" 2>/dev/null
echo
echo "================ EXECTEST REPORT ================"
cat "$RES/exec_test.log" 2>/dev/null || echo "(no report file)"
echo "================ journals ================"
echo "--- Experts journal"
iconv -f UTF-16LE -t UTF-8 "$M/MQL5/logs/$D.log" 2>/dev/null | tr -d '\r' | tail -30
echo "--- terminal journal (trade lines)"
iconv -f UTF-16LE -t UTF-8 "$M/logs/$D.log" 2>/dev/null | tr -d '\r' | grep -iE "order|deal|trade|expert|error|invalid" | tail -20
echo
echo "=== live deployment unchanged?"
md5sum -c "$RES/live_before_order.md5" 2>&1 || echo "!!! A LIVE FILE CHANGED"
grep -E "time_gmt|balance=|equity=|positions=" "/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/heartbeat.txt"
echo "### RUN 2 DONE $(date -u '+%F %T')"
