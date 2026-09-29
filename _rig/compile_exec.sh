#!/bin/bash
# Compile ExecTest.mq5 inside the rig with MetaEditor (run as root; it drops to mt5).
M="/home/mt5/.wine-test/drive_c/Program Files/MetaTrader 5 TEST"
cd "$M" || exit 1
echo "--- source present:"
ls -la "MQL5/Experts/ExecTest/" 2>&1
echo "--- compile:"
sudo -u mt5 -H env DISPLAY=:99 WINEPREFIX=/home/mt5/.wine-test WINEDEBUG=-all \
  WINEDLLOVERRIDES="mscoree=;mshtml=" bash -lc \
  "cd '$M' && timeout 240 wine MetaEditor64.exe /portable /compile:'MQL5\\Experts\\ExecTest\\ExecTest.mq5' /log:'MQL5\\Experts\\ExecTest\\compile.log'"
echo "rc=$?"
echo "--- result folder:"
ls -la "MQL5/Experts/ExecTest/" 2>&1
echo "--- compile log:"
if [ -f "MQL5/Experts/ExecTest/compile.log" ]; then
  iconv -f UTF-16LE -t UTF-8 "MQL5/Experts/ExecTest/compile.log" 2>/dev/null | tr -d '\r' | tail -25
else
  echo "(no compile.log)"
fi
echo "--- metaeditor journal tail:"
find . -maxdepth 3 -name "metaeditor.log" -newermt "-10 minutes" 2>/dev/null
