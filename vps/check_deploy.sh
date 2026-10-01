#!/bin/bash
MT5="/home/mt5/.wine/drive_c/Program Files/MetaTrader 5"
F="/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"
L=$(ls -t "$MT5"/logs/*.log | head -1)
iconv -f UTF-16LE -t UTF-8 "$L" | grep -E "inputs read" | tail -1
echo "--- events.log (last 5)"
tail -5 "$F/events.log"
echo "--- heartbeat"
grep -E "regime|history_ready|halted|connected=" "$F/heartbeat.txt"
