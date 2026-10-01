#!/bin/bash
# Gold Trend Breakout bot - step 5: finish the Wine prefix update without Mono/Gecko, restart MT5.
set -uo pipefail
pkill -f 'bash -c wineboot -u' 2>/dev/null
sudo -u mt5 env WINEPREFIX=/home/mt5/.wine wineserver -k 2>/dev/null
sleep 2
sudo -u mt5 -H env WINEPREFIX=/home/mt5/.wine WINEDEBUG=-all DISPLAY=:99 WINEDLLOVERRIDES="mscoree=;mshtml=" \
  bash -c 'timeout 120 wineboot -u >/dev/null 2>&1; wineserver -w'
install -o mt5 -g mt5 -m 750 /root/gtb_deploy/run_mt5.sh /home/mt5/gtb/run_mt5.sh
systemctl restart gtb-mt5.service
sleep 45
M="/home/mt5/.wine/drive_c/Program Files/MetaTrader 5"
L=$(ls -t "$M"/logs/*.log | head -1)
iconv -f UTF-16LE -t UTF-8 "$L" | tail -12
echo "--- EA log"
L=$(ls -t "$M"/MQL5/Logs/*.log 2>/dev/null | head -1)
[ -n "$L" ] && iconv -f UTF-16LE -t UTF-8 "$L" | tail -8 || echo "no EA log yet"
systemctl is-active gtb-mt5
