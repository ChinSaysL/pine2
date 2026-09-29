#!/bin/bash
# Status after the aborted live-install test: what loaded, what was left behind, is the live EA back?
TST=/home/mt5/.wine-test
M="$TST/drive_c/Program Files/MetaTrader 5 TEST"
L="/home/mt5/.wine/drive_c/Program Files/MetaTrader 5"
LF="/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"
D=$(date -u +%Y%m%d)

echo "=== now $(date -u '+%F %T')"
echo "=== services"; systemctl is-active gtb-mt5 gtb-mt5-nq gtb-xvfb gtb-vnc gtb-notifier
echo
echo "=== LIVE account state (from the EA heartbeat)"
cat "$LF/heartbeat.txt"
echo
echo "=== live terminal journal: ExecTest / order / deal lines"
iconv -f UTF-16LE -t UTF-8 "$L/logs/$D.log" 2>/dev/null | tr -d '\r' | grep -inE "exectest|order|deal|performed" | tail -25
echo
echo "=== live EA journal (gold) tail"
iconv -f UTF-16LE -t UTF-8 "$L/MQL5/logs/$D.log" 2>/dev/null | tr -d '\r' | tail -8
echo
echo "=== live Common folder (any exec_test.log left behind?)"
ls -la "$LF"
echo "--- content if any:"; cat "$LF/exec_test.log" 2>/dev/null
echo
echo "=== rig: does it still exist?"
ls -d "$TST" 2>&1
echo "=== rig terminal journal: ExecTest lines"
iconv -f UTF-16LE -t UTF-8 "$M/logs/$D.log" 2>/dev/null | tr -d '\r' | grep -inE "exectest|order|deal|performed|authoriz" | tail -25
echo
echo "=== rig Common folder"
ls -la "$TST/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout" 2>/dev/null
echo "--- rig report:"; cat "$TST/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/exec_test.log" 2>/dev/null
echo
echo "=== ExecTest EA installed anywhere?"
ls -la "$L/MQL5/Experts/ExecTest/" 2>&1
ls -la "$M/MQL5/Experts/ExecTest/" 2>&1
echo "=== leftover temp config?"
ls -la "$L/config/exec_test.ini" 2>&1
echo "=== processes"
pgrep -u mt5 -af "terminal64" | cut -c1-100
