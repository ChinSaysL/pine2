#!/bin/bash
M1="/home/mt5/.wine/drive_c/Program Files/MetaTrader 5"; M2="/home/mt5/.wine/drive_c/Program Files/MetaTrader 5 NQ"
md5sum "$M1/MQL5/Experts/GoldTrendBreakout/GoldTrendBreakout.mq5" "$M2/MQL5/Experts/NasdaqORB/NasdaqORB.mq5" /root/gtb_deploy/gtb_live.set /root/gtb_deploy/nq_live.set /usr/local/bin/gtb-notifier.py | sed 's#  .*/#  #'
grep positions "/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/heartbeat.txt" "/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/nasdaq_heartbeat.txt" | sed 's#.*/##'
date -u
