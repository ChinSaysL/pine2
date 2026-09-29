#!/bin/bash
# Recompile ExecTest with an explicit log path so we can read the error message.
M="/home/mt5/.wine-test/drive_c/Program Files/MetaTrader 5 TEST"
ZLOG='Z:\root\ce.log'
rm -f /root/ce.log
cd "$M" || exit 1
sudo -u mt5 -H env DISPLAY=:99 WINEPREFIX=/home/mt5/.wine-test WINEDEBUG=-all WINEDLLOVERRIDES="mscoree=;mshtml=" \
  bash -c "cd '$M' && timeout 240 wine MetaEditor64.exe /portable /compile:'MQL5\\Experts\\ExecTest\\ExecTest.mq5' /log:'$ZLOG'"
echo "rc=$?"
echo "--- log file(s) found:"
ls -la /root/ce.log 2>&1
find /home/mt5/.wine-test -name "compile*.log" -newermt "-15 minutes" 2>/dev/null
find /home/mt5/.wine -name "compile.log" -path "*ExecTest*" 2>/dev/null
echo "--- log content:"
if [ -f /root/ce.log ]; then iconv -f UTF-16LE -t UTF-8 /root/ce.log 2>/dev/null | tr -d '\r' | tail -30
elif [ -f "$M/MQL5/Experts/ExecTest/compile.log" ]; then iconv -f UTF-16LE -t UTF-8 "$M/MQL5/Experts/ExecTest/compile.log" 2>/dev/null | tr -d '\r' | tail -30
else echo "(still no log - showing the metaeditor journal)"; tail -c 2000 "$M/logs/metaeditor.log" 2>/dev/null | iconv -f UTF-16LE -t UTF-8 2>/dev/null; fi
echo "--- .ex5 present?"
ls -la "$M/MQL5/Experts/ExecTest/" 2>&1
