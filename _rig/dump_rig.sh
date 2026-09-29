#!/bin/bash
# Dump the rig journals + the exec test log (diagnostic while the order test runs/finished).
TST=/home/mt5/.wine-test
M="$TST/drive_c/Program Files/MetaTrader 5 TEST"
D=$(date -u +%Y%m%d)
C="$TST/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"
echo "=== now: $(date -u '+%F %T')"
echo "=== ExecTest.ex5 present: $(ls -la "$M/MQL5/Experts/ExecTest/" 2>&1 | tr '\n' ' ')"
echo "=== rig terminal processes:"
pgrep -u mt5 -af "MetaTrader 5 TEST" | cut -c1-90
echo "=== rig Common folder:"
ls -la "$C" 2>&1
echo "=== exec_test.log:"
cat "$C/exec_test.log" 2>/dev/null
echo "=== rig Experts journal (last 30):"
iconv -f UTF-16LE -t UTF-8 "$M/MQL5/logs/$D.log" 2>/dev/null | tr -d '\r' | tail -30
echo "=== rig terminal journal (last 25):"
iconv -f UTF-16LE -t UTF-8 "$M/logs/$D.log" 2>/dev/null | tr -d '\r' | tail -25
echo "=== live heartbeat (untouched?):"
grep -E "time_gmt|balance=|equity=|positions=" "/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/heartbeat.txt"
