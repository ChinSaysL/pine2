#!/bin/bash
TST=/home/mt5/.wine-test
M="$TST/drive_c/Program Files/MetaTrader 5 TEST"
D=$(date -u +%Y%m%d)
echo "=== now: $(date -u '+%F %T')"
echo "=== rig terminal journal: Network / Startup / Experts / Tester lines (all)"
iconv -f UTF-16LE -t UTF-8 "$M/logs/$D.log" 2>/dev/null | tr -d '\r' | grep -nE "Network|Startup|Experts|Tester|MQL5|login|account|scan|connect" | tail -30
echo
echo "=== live gold terminal journal: Network lines in the same window (did the rig take the session?)"
iconv -f UTF-16LE -t UTF-8 "/home/mt5/.wine/drive_c/Program Files/MetaTrader 5/logs/$D.log" 2>/dev/null | tr -d '\r' | grep -nE "authoriz|disconnect|no connection" | tail -12
echo
echo "=== is the live gold EA still connected?"
grep -E "time_gmt|connected|positions=" /home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/heartbeat.txt
echo
echo "=== rig terminal process + its open journal"
pgrep -u mt5 -af "MetaTrader 5 TEST" | cut -c1-80
echo "=== rig exec_test.log:"
cat "$TST/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/exec_test.log" 2>/dev/null || echo "(none yet)"
echo "=== wine windows on :99"
sudo -u mt5 -H env DISPLAY=:99 xdotool search --name "" getwindowname %@ 2>/dev/null | head -20 || echo "(xdotool not installed)"
