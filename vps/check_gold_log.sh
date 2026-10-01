#!/bin/bash
M="/home/mt5/.wine/drive_c/Program Files/MetaTrader 5"
L=$(ls -t "$M"/MQL5/Logs/*.log | head -1)
iconv -f UTF-16LE -t UTF-8 "$L" | grep -E "START|REGIME|news|WARNING" | tail -6
tail -3 "/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/events.log"
