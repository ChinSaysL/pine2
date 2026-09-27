#!/bin/bash
# EA liveness: heartbeat age, recent events, EA journal.
M="/home/mt5/.wine/drive_c/Program Files/MetaTrader 5"
F="/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"
now=$(date +%s)
hb=$(stat -c %Y "$F/heartbeat.txt" 2>/dev/null || echo 0)
echo "heartbeat age: $(( (now - hb) / 60 )) min ($(date -u -d @"$hb" '+%H:%M:%S') UTC, now $(date -u '+%H:%M:%S'))"
grep -E 'time_gmt|connected|login|server=' "$F/heartbeat.txt"
echo "--- events.log"
tail -8 "$F/events.log"
echo "--- EA journal files"
ls -la "$M/MQL5/Logs/" 2>&1 | tail -5
for L in $(ls -t "$M"/MQL5/Logs/*.log 2>/dev/null | head -1); do iconv -f UTF-16LE -t UTF-8 "$L" | tail -10; done
echo "--- terminal log, last 6"
L=$(ls -t "$M"/logs/*.log | head -1); iconv -f UTF-16LE -t UTF-8 "$L" | tail -6
